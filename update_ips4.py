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

def get_all_existing_cname_records():
    """获取指定域名下所有的 CNAME 记录，不区分线路"""
    print(f"正在查询域名 {DOMAIN_NAME} 的所有现有 CNAME 记录...")
    try:
        request = ListRecordSetsByZoneRequest(
            zone_id=zone_id,
            name=DOMAIN_NAME + ".",
            type="CNAME"
        )
        response = dns_client.list_record_sets_by_zone(request)
        
        print(f"查询到 {len(response.recordsets)} 条已存在的 CNAME 记录。")
        return response.recordsets
    except exceptions.ClientRequestException as e:
        print(f"错误: 查询所有 CNAME 记录时发生错误: {e}")
        return []

def delete_dns_record(record):
    """删除指定的 DNS 记录"""
    try:
        request = DeleteRecordSetRequest(zone_id=zone_id, recordset_id=record.id)
        dns_client.delete_record_set(request)
        print(f"成功删除旧的 {record.type} 记录: {record.id} (线路: {getattr(record, 'line', 'N/A')}, 值: {record.records[0]})")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 删除记录 {record.id} 时失败: {e}")
        return False

def create_cname_record(line_id, cname_target):
    """为指定线路创建一条 CNAME 解析记录"""
    print(f"准备为线路 '{line_id}' 创建 CNAME 记录，指向 {cname_target}...")
    try:
        body = CreateRecordSetRequestBody(
            name=DOMAIN_NAME + ".",
            type="CNAME",
            records=[cname_target],
            ttl=60
        )
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
    print("--- 开始更新华为云三网优化 CNAME 解析记录 (批量删除后创建) ---")
    
    if not DOMAIN_NAME:
        print("错误: 缺少必要的 DOMAIN_NAME 环境变量。")
        return

    if not init_huawei_dns_client() or not get_zone_id():
        print("华为云客户端初始化或 Zone ID 获取失败，任务终止。")
        return

    # 1. 从所有 API 获取新的 CNAME 目标
    print("\n--- 步骤 1: 从 API 获取所有线路的目标 CNAME ---")
    new_targets = {}
    for line_name, (line_id, api_url) in API_CONFIG.items():
        print(f"正在获取【{line_name}】线路的目标...")
        target = get_cname_target_from_api(api_url)
        if target:
            new_targets[line_id] = target
        else:
            print(f"警告: 未能为【{line_name}】线路获取 CNAME 目标，将跳过此线路的创建。")

    if not new_targets:
        print("错误: 未能从任何 API 获取到有效的 CNAME 目标，任务终止。")
        return

    # 2. 获取并删除该域名下所有的旧 CNAME 记录
    print(f"\n--- 步骤 2: 删除域名 {DOMAIN_NAME} 下所有已存在的 CNAME 记录 ---")
    existing_records = get_all_existing_cname_records()
    if existing_records:
        for record in existing_records:
            delete_dns_record(record)
    else:
        print("没有需要删除的旧 CNAME 记录。")

    # 3. 依次创建新的 CNAME 记录
    print(f"\n--- 步骤 3: 为各线路创建新的 CNAME 记录 ---")
    success_count = 0
    failure_count = 0
    for line_id, cname_target in new_targets.items():
        # 通过 line_id 反查 line_name 用于打印日志
        line_name = next((k for k, v in API_CONFIG.items() if v[0] == line_id), "未知")
        print(f"--- 正在为【{line_name}】({line_id}) 线路创建记录 ---")
        if create_cname_record(line_id, cname_target):
            success_count += 1
        else:
            failure_count += 1

    # 4. 总结报告
    print(f"\n{'='*20} 所有线路处理完毕 {'='*20}")
    print(f"总结: 成功 {success_count} 条, 失败 {failure_count} 条。")


if __name__ == '__main__':
    main()
