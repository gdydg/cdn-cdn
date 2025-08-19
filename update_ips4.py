# update_cname_by_3_networks.py
import os
import time
import requests

# 导入华为云 SDK 核心库
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions
# 导入华为云 DNS 服务库
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

# --- 从 GitHub Secrets 读取配置 ---
# 华为云访问密钥 ID (Access Key ID)
HUAWEI_CLOUD_AK = os.environ.get('HUAWEI_CLOUD_AK')
# 华为云秘密访问密钥 (Secret Access Key)
HUAWEI_CLOUD_SK = os.environ.get('HUAWEI_CLOUD_SK')
# 华为云 Project ID
HUAWEI_CLOUD_PROJECT_ID = os.environ.get('HUAWEI_CLOUD_PROJECT_ID')
# 华为云托管的公网域名 (Zone Name)
HUAWEI_CLOUD_ZONE_NAME = os.environ.get('HUAWEI_CLOUD_ZONE_NAME')
# 需要更新解析的完整域名
DOMAIN_NAME = os.environ.get('DOMAIN_NAME')

# --- 三网优选 CNAME 的 API 地址 ---
# <-- 请将这里替换为您的 API 地址 -->
# 脚本会读取每个 API 返回内容的第一行作为对应线路的 CNAME 目标
API_CONFIG = {
    # 线路名称: (线路ID, API地址)
    "电信": ("dianxin", 'https://raw.githubusercontent.com/gdydg/cdn-cdn/refs/heads/main/cname.txt'),
    "联通": ("liantong", 'https://raw.githubusercontent.com/gdydg/cdn-cdn/refs/heads/main/cname.txt'),
    "移动": ("yidong", 'https://raw.githubusercontent.com/gdydg/cdn-cdn/refs/heads/main/cname.txt')
}

# --- 全局变量 ---
dns_client = None
zone_id = None

def init_huawei_dns_client():
    """初始化华为云 DNS 客户端"""
    global dns_client
    if not all([HUAWEI_CLOUD_AK, HUAWEI_CLOUD_SK, HUAWEI_CLOUD_PROJECT_ID]):
        print("错误: 缺少华为云 AK, SK 或 Project ID，请检查 GitHub Secrets 配置。")
        return False
    
    credentials = BasicCredentials(ak=HUAWEI_CLOUD_AK,
                                     sk=HUAWEI_CLOUD_SK,
                                     project_id=HUAWEI_CLOUD_PROJECT_ID)
    
    try:
        dns_client = DnsClient.new_builder() \
            .with_credentials(credentials) \
            .with_region(DnsRegion.value_of("cn-east-3")) \
            .build()
        print("华为云 DNS 客户端初始化成功。")
        return True
    except Exception as e:
        print(f"错误: 初始化华为云 DNS 客户端失败: {e}")
        return False

def get_zone_id():
    """根据 Zone Name 获取 Zone ID"""
    global zone_id
    if not HUAWEI_CLOUD_ZONE_NAME:
        print("错误: 未配置 HUAWEI_CLOUD_ZONE_NAME 环境变量。")
        return False
        
    print(f"正在查询公网域名 '{HUAWEI_CLOUD_ZONE_NAME}' 的 Zone ID...")
    try:
        request = ListPublicZonesRequest()
        response = dns_client.list_public_zones(request)
        for z in response.zones:
            if z.name == HUAWEI_CLOUD_ZONE_NAME + ".":
                zone_id = z.id
                print(f"成功找到 Zone ID: {zone_id}")
                return True
        print(f"错误: 未能找到名为 '{HUAWEI_CLOUD_ZONE_NAME}' 的公网域名。")
        return False
    except exceptions.ClientRequestException as e:
        print(f"错误: 查询 Zone ID 时发生 API 错误: {e}")
        return False

def get_cname_target_from_api(api_url):
    """从 API 获取优选 CNAME 目标"""
    print(f"正在从 {api_url} 获取 CNAME 目标...")
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        if not lines or not lines[0].strip():
            print("错误: 从 API 获取到的内容为空或无效。")
            return None
        
        cname_target = lines[0].strip()
        if not cname_target.endswith('.'):
            cname_target += '.'
        
        print(f"成功获取到 CNAME 目标: {cname_target}")
        return cname_target
    except requests.RequestException as e:
        print(f"错误: 请求优选 CNAME 时发生错误: {e}")
        return None

def get_existing_records_by_line(line_id):
    """获取指定线路上已存在的 A 或 CNAME 记录"""
    print(f"正在查询线路 '{line_id}' 上域名 {DOMAIN_NAME} 的现有 A 和 CNAME 记录...")
    try:
        request = ListRecordSetsByZoneRequest(
            zone_id=zone_id,
            name=DOMAIN_NAME + "."
        )
        request.line = line_id
        
        response = dns_client.list_record_sets_by_zone(request)
        
        # 增加严格的客户端线路匹配，防止 API 返回非指定线路的记录 (如默认线路)
        # 确保返回的记录的 line 属性与我们查询的 line_id 完全一致
        filtered_records = [
            r for r in response.recordsets 
            if r.type in ["A", "CNAME"] and hasattr(r, 'line') and r.line == line_id
        ]
        
        print(f"查询并严格匹配后，找到 {len(filtered_records)} 条【{line_id}】线路的 A 或 CNAME 记录。")
        return filtered_records
    except exceptions.ClientRequestException as e:
        print(f"错误: 查询线路 '{line_id}' 的 DNS 记录时发生错误: {e}")
        return []

def delete_dns_record(record):
    """删除指定的 DNS 记录"""
    try:
        request = DeleteRecordSetRequest(zone_id=zone_id, recordset_id=record.id)
        dns_client.delete_record_set(request)
        print(f"成功删除旧的 {record.type} 记录: {record.id} (线路: {record.line}, 值: {record.records[0]})")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 删除记录 {record.id} 时失败: {e}")
        return False

def create_cname_record(line_id, cname_target):
    """为指定线路创建一条 CNAME 解析记录"""
    print(f"准备为线路 '{line_id}' 创建 CNAME 记录，指向 {cname_target}...")
    try:
        # ★★★ 关键修复点 ★★★
        # 先创建 body 对象，不传入 line 参数
        body = CreateRecordSetRequestBody(
            name=DOMAIN_NAME + ".",
            type="CNAME",
            records=[cname_target],
            ttl=60
        )
        # 再将 line 作为对象的属性来设置
        body.line = line_id
        
        request = CreateRecordSetRequest(zone_id=zone_id, body=body)
        dns_client.create_record_set(request)
        print(f"成功为线路 '{line_id}' 创建了 CNAME 记录。")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 为线路 '{line_id}' 创建 CNAME 解析记录时失败: {e}")
        return False

def main():
    """主执行函数"""
    print("--- 开始更新华为云三网优化 CNAME 解析记录 ---")
    
    if not DOMAIN_NAME:
        print("错误: 缺少必要的 DOMAIN_NAME 环境变量。")
        return

    if not init_huawei_dns_client() or not get_zone_id():
        print("华为云客户端初始化或 Zone ID 获取失败，任务终止。")
        return

    for line_name, (line_id, api_url) in API_CONFIG.items():
        print(f"\n{'='*20} 开始处理【{line_name}】线路 {'='*20}")

        # 1. 从 API 获取新的 CNAME 目标
        new_cname_target = get_cname_target_from_api(api_url)
        if not new_cname_target:
            print(f"未能为【{line_name}】线路获取 CNAME 目标，跳过此线路。")
            continue

        # 2. 获取该线路上已存在的记录
        existing_records = get_existing_records_by_line(line_id)
        
        # 检查是否需要更新 (如果记录已存在且目标相同，则跳过)
        is_already_updated = False
        if len(existing_records) == 1 and existing_records[0].type == "CNAME" and existing_records[0].records[0] == new_cname_target:
             print(f"【{line_name}】线路记录已是最新，无需更新。")
             is_already_updated = True
        
        if is_already_updated:
            continue

        if existing_records:
            print(f"--- 开始删除【{line_name}】线路的旧记录 ---")
            for record in existing_records:
                delete_dns_record(record)
        
        # 3. 创建新的 CNAME 记录
        print(f"--- 开始为【{line_name}】线路创建新记录 ---")
        if create_cname_record(line_id, new_cname_target):
            print(f"--- 【{line_name}】线路更新成功 ---")
        else:
            print(f"--- 【{line_name}】线路更新失败 ---")

    print(f"\n{'='*20} 所有线路处理完毕 {'='*20}")


if __name__ == '__main__':
    main()
