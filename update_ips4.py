import os
import requests
import time

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

# --- 环境变量配置 ---
HUAWEI_CLOUD_AK = os.environ.get('HUAWEI_CLOUD_AK')
HUAWEI_CLOUD_SK = os.environ.get('HUAWEI_CLOUD_SK')
HUAWEI_CLOUD_PROJECT_ID = os.environ.get('HUAWEI_CLOUD_PROJECT_ID')
HUAWEI_CLOUD_ZONE_NAME = os.environ.get('HUAWEI_CLOUD_ZONE_NAME')
DOMAIN_NAME = os.environ.get('DOMAIN_NAME')

# --- 三网 API 地址 ---
IP_API_URLS = {
    "Yidong": "https://raw.githubusercontent.com/gdydg/ip/refs/heads/main/cm.txt",    # 移动线路 API
    "Dianxin": "https://raw.githubusercontent.com/gdydg/ip/refs/heads/main/cu.txt",   # 电信线路 API
    "Liantong": "https://raw.githubusercontent.com/gdydg/ip/refs/heads/main/ct.txt"   # 联通线路 API
}

# --- 三网线路代码 ---
ISP_LINES = {
    "移动": "Yidong",
    "电信": "Dianxin",
    "联通": "Liantong"
}

dns_client = None
zone_id = None

def init_huawei_dns_client():
    global dns_client
    if not all([HUAWEI_CLOUD_AK, HUAWEI_CLOUD_SK, HUAWEI_CLOUD_PROJECT_ID]):
        print("错误: 缺少 AK、SK 或 Project ID。")
        return False

    credentials = BasicCredentials(
        ak=HUAWEI_CLOUD_AK,
        sk=HUAWEI_CLOUD_SK,
        project_id=HUAWEI_CLOUD_PROJECT_ID
    )

    try:
        dns_client = DnsClient.new_builder() \
            .with_credentials(credentials) \
            .with_region(DnsRegion.value_of("cn-east-3")) \
            .build()
        print("DNS 客户端初始化成功。")
        return True
    except Exception as e:
        print(f"初始化 DNS 客户端失败: {e}")
        return False

def get_zone_id():
    global zone_id
    if not HUAWEI_CLOUD_ZONE_NAME:
        print("错误: 未配置 Zone Name。")
        return False

    print(f"查询 Zone ID for '{HUAWEI_CLOUD_ZONE_NAME}'...")
    try:
        request = ListPublicZonesRequest()
        response = dns_client.list_public_zones(request)
        for z in response.zones:
            if z.name == HUAWEI_CLOUD_ZONE_NAME + ".":
                zone_id = z.id
                print(f"找到 Zone ID: {zone_id}")
                return True
        print("未找到匹配的 Zone。")
        return False
    except exceptions.ClientRequestException as e:
        print(f"查询 Zone ID 出错: {e}")
        return False

def get_cname_target(api_url):
    if not api_url:
        print("错误: API 地址未配置。")
        return None

    print(f"从 {api_url} 获取 CNAME 目标...")
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                cname = line.split('#')[0].strip()
                print(f"获取 CNAME 目标成功: {cname}")
                return cname
        print("API 返回内容为空或无效。")
        return None
    except requests.RequestException as e:
        print(f"请求 CNAME 目标失败: {e}")
        return None

def get_existing_records_for_line(line_code):
    print(f"查询线路 {line_code} 的现有 CNAME 记录...")
    try:
        request = ListRecordSetsWithLineRequest()
        request.zone_id = zone_id
        request.name = DOMAIN_NAME + "."
        request.type = "CNAME"
        request.line_id = line_code

        response = dns_client.list_record_sets_with_line(request)
        if response.recordsets:
            print(f"找到 {len(response.recordsets)} 条记录。")
            return response.recordsets
        else:
            print("无记录。")
            return []
    except exceptions.ClientRequestException as e:
        print(f"查询记录失败: {e}")
        return []

def update_cname_record_set(record_id, cname_target):
    print(f"更新记录 {record_id} 为 CNAME: {cname_target}")
    try:
        body = UpdateRecordSetReq(
            ttl=60,
            records=[cname_target]
        )
        request = UpdateRecordSetRequest()
        request.zone_id = zone_id
        request.recordset_id = record_id
        request.body = body
        dns_client.update_record_set(request)
        print("更新成功。")
        return True
    except exceptions.ClientRequestException as e:
        print(f"更新失败: {e}")
        return False

def create_cname_record_set(cname_target, line_code):
    print(f"创建线路 {line_code} 的 CNAME 记录: {cname_target}")
    try:
        body = CreateRecordSetWithLineRequestBody(
            name=DOMAIN_NAME + ".",
            type="CNAME",
            records=[cname_target],
            ttl=60,
            line=line_code
        )
        request = CreateRecordSetWithLineRequest()
        request.zone_id = zone_id
        request.body = body
        dns_client.create_record_set_with_line(request)
        print("创建成功。")
        return True
    except exceptions.ClientRequestException as e:
        print(f"创建失败: {e}")
        return False

def main():
    print("--- 开始三网 CNAME 优化 ---")

    if not DOMAIN_NAME:
        print("错误: 缺少 DOMAIN_NAME。")
        return

    if not init_huawei_dns_client() or not get_zone_id():
        print("初始化失败。")
        return
    for line_name, line_code in ISP_LINES.items():
        print(f"\n处理线路: {line_name} ({line_code})")

        api_url = IP_API_URLS.get(line_code)
        if not api_url:
            print("未配置 API URL，跳过。")
            continue

        cname_target = get_cname_target(api_url)
        if not cname_target:
            print("未获取到 CNAME 目标，跳过。")
            continue

        existing_records = get_existing_records_for_line(line_code)
        if existing_records:
            record_id = existing_records[0].id
            update_cname_record_set(record_id, cname_target)
        else:
            create_cname_record_set(cname_target, line_code)

        time.sleep(2)

    print("\n--- 三网 CNAME 优化完成 ---")

if __name__ == '__main__':
    main()
