import os
import requests
import json
import time

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
# (可选) 需要解析的IP数量
MAX_IPS = os.environ.get('MAX_IPS')

# --- 优选 IP 的 API 地址 (请直接在此处修改) ---
IP_API_URLS = {
    "Yidong": "https://ipdb.api.030101.xyz/?type=bestcf&country=true",    # 移动线路 API
    "Dianxin": "https://ipdb.api.030101.xyz/?type=bestcf&country=true", # 电信线路 API
    "Liantong": "https://ipdb.api.030101.xyz/?type=bestcf&country=true" # 联通线路 API
}

# --- 定义运营商线路 ---
ISP_LINES = {
    "移动": "Yidong",
    "电信": "Dianxin",
    "联通": "Liantong"
}

# --- 全局变量 ---
dns_client = None
zone_id = None

def init_huawe_dns_client():
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
        print("错误: 未配置 HUAWEI_CLOUD_ZONE_NAME。")
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

def get_preferred_ips(api_url):
    """从指定的 API 获取优选 IP 列表"""
    # 检查URL是否还是占位符
    if "请在这里填入" in api_url:
        print(f"错误: API 地址尚未配置: {api_url}")
        return []

    print(f"正在从 {api_url} 获取优选 IP...")
    retry_count = 3
    retry_delay = 10
    for attempt in range(retry_count):
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            lines = response.text.strip().split('\n')
            valid_ips = [line.split('#')[0].strip() for line in lines if line.strip() and not line.startswith('#')]

            if not valid_ips:
                print("警告: 从 API 获取到的内容为空或无效。")
                return []
            
            print(f"成功获取并解析了 {len(valid_ips)} 个优选 IP。")

            if MAX_IPS and MAX_IPS.isdigit():
                max_ips_count = int(MAX_IPS)
                if 0 < max_ips_count < len(valid_ips):
                    print(f"根据 MAX_IPS={max_ips_count} 的设置，将只使用前 {max_ips_count} 个 IP。")
                    return valid_ips[:max_ips_count]
            
            return valid_ips
        except requests.RequestException as e:
            print(f"错误: 请求优选 IP 时发生错误: {e}")
            if attempt < retry_count - 1:
                print(f"将在 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print("已达到最大重试次数，获取 IP 失败。")
                return []
    return []

def get_existing_records_for_line(line_code):
    """获取指定线路下，当前域名的 A 记录"""
    print(f"正在使用线路接口查询域名 {DOMAIN_NAME} (线路: {line_code}) 的现有 A 记录...")
    try:
        request = ListRecordSetsWithLineRequest()
        request.zone_id = zone_id
        request.name = DOMAIN_NAME + "."
        request.type = "A"
        request.line_id = line_code
        
        response = dns_client.list_record_sets_with_line(request)
        
        if response.recordsets:
            print(f"查询到 {len(response.recordsets)} 条属于线路 '{line_code}' 的记录。")
            return response.recordsets
        else:
            print(f"线路 '{line_code}' 下没有已存在的 A 记录。")
            return []
    except exceptions.ClientRequestException as e:
        print(f"错误: 查询线路 DNS 记录时发生错误: {e}")
        return []

def update_dns_record_set(record_id, ip_list):
    """更新指定的 DNS 记录集"""
    print(f"准备将记录 {record_id} 的 IP 更新为新的列表...")
    try:
        # 更新记录只需要提供 TTL 和 IP 列表
        body = UpdateRecordSetReq(
            ttl=1,
            records=ip_list
        )
        request = UpdateRecordSetRequest()
        request.zone_id = zone_id
        request.recordset_id = record_id
        request.body = body
        
        dns_client.update_record_set(request)
        print(f"成功更新记录 {record_id}。")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 更新记录 {record_id} 时失败: {e}")
        if hasattr(e, 'error_msg'):
            print(f"API 返回信息: {e.error_msg}")
        return False

def create_dns_record_set(ip_list, line_code):
    """创建新的 DNS 记录集"""
    print(f"准备将 {len(ip_list)} 个 IP 创建到线路 '{line_code}' 的一个新解析记录集中...")
    try:
        body = CreateRecordSetWithLineRequestBody(
            name=DOMAIN_NAME + ".", 
            type="A", 
            records=ip_list, 
            ttl=1,
            line=line_code
        )
        
        request = CreateRecordSetWithLineRequest()
        request.zone_id = zone_id
        request.body = body
        dns_client.create_record_set_with_line(request)

        print(f"成功为 {DOMAIN_NAME} (线路: {line_code}) 创建了新的 A 记录。")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 创建解析记录集时失败: {e}")
        if hasattr(e, 'error_msg'):
            print(f"API 返回信息: {e.error_msg}")
        return False

def main():
    """主执行函数"""
    print("--- 开始更新华为云优选 IP ---")
    
    if not all([DOMAIN_NAME]):
        print("错误: 缺少必要的 DOMAIN_NAME 环境变量。")
        return

    if not init_huawe_dns_client() or not get_zone_id():
        print("华为云客户端初始化或 Zone ID 获取失败，任务终止。")
        return

    # 遍历所有定义的运营商线路
    for line_name, line_code in ISP_LINES.items():
        print(f"\n--- 正在处理线路: {line_name} ({line_code}) ---")

        # 获取当前线路对应的 API URL
        current_api_url = IP_API_URLS.get(line_code)
        if not current_api_url:
            print(f"警告: 未为线路 '{line_name}' ({line_code}) 配置 API URL。跳过此线路。")
            continue

        # 为当前线路获取新的 IP 列表
        new_ips = get_preferred_ips(current_api_url)
        if not new_ips:
            print(f"未能从 {current_api_url} 获取新的 IP 地址，跳过此线路。")
            continue

        # 1. 查询当前线路下的旧记录
        existing_records = get_existing_records_for_line(line_code)
        
        if existing_records:
            # 如果存在记录，则更新第一条记录
            # 华为云似乎会为同一线路创建多个 recordset，我们只更新第一个，其他的可以手动清理
            record_to_update = existing_records[0]
            print(f"--- 发现旧记录，将更新记录 ID: {record_to_update.id} ---")
            update_dns_record_set(record_to_update.id, new_ips)
        else:
            # 如果不存在记录，则创建新记录
            print(f"--- 未发现旧记录，将创建新记录 ---")
            create_dns_record_set(new_ips, line_code)
        
        # 增加延迟，避免API调用过于频繁
        time.sleep(2)
    
    print("\n--- 所有线路更新完成 ---")


if __name__ == '__main__':
    main()
