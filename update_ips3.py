# update_cname_by_line.py
import os
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

# --- CNAME 目标地址 ---
CNAME_TARGET = 'cf.090227.xyz.' # CNAME 记录值末尾需要有一个点

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
        print("错误: 未配置 HUAWEI_CLOUD_ZONE_NAME。")
        return False
        
    print(f"正在查询公网域名 '{HUAWEI_CLOUD_ZONE_NAME}' 的 Zone ID...")
    try:
        request = ListPublicZonesRequest()
        response = dns_client.list_public_zones(request)
        for z in response.zones:
            # 华为云返回的 zone name 会自带一个点
            if z.name == HUAWEI_CLOUD_ZONE_NAME + ".":
                zone_id = z.id
                print(f"成功找到 Zone ID: {zone_id}")
                return True
        print(f"错误: 未能找到名为 '{HUAWEI_CLOUD_ZONE_NAME}' 的公网域名。")
        return False
    except exceptions.ClientRequestException as e:
        print(f"错误: 查询 Zone ID 时发生 API 错误: {e}")
        return False

def get_existing_cname_record():
    """获取当前域名【全网默认】的 CNAME 记录"""
    print(f"正在查询域名 {DOMAIN_NAME} 的现有【全网默认】DNS CNAME 记录...")
    try:
        request = ListRecordSetsByZoneRequest(
            zone_id=zone_id,
            name=DOMAIN_NAME + ".",
            type="CNAME" 
        )
        response = dns_client.list_record_sets_by_zone(request)
        
        for record in response.recordsets:
            # 检查是否为“全网默认”线路
            if not hasattr(record, 'line') or record.line == "default":
                print(f"查询到已存在的【全网默认】CNAME 记录，ID: {record.id}, 指向: {record.records[0]}")
                return record # 返回找到的第一个默认线路的 CNAME 记录

        print("未查询到已存在的【全网默认】CNAME 记录。")
        return None
    except exceptions.ClientRequestException as e:
        print(f"错误: 查询 DNS 记录时发生错误: {e}")
        return None

def delete_dns_record(record_id, record_value):
    """删除指定的 DNS 记录"""
    try:
        request = DeleteRecordSetRequest(zone_id=zone_id, recordset_id=record_id)
        dns_client.delete_record_set(request)
        print(f"成功删除旧的 CNAME 记录: {record_id} (指向 {record_value})")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 删除记录 {record_id} 时失败: {e}")
        return False

def create_cname_record():
    """为【全网默认】线路创建一条 CNAME 解析记录"""
    print(f"准备为 {DOMAIN_NAME} 的【全网默认】线路创建 CNAME 记录，指向 {CNAME_TARGET}...")
    try:
        # ★★★ 关键修复点 ★★★
        # 先创建 body 对象，不传入 line 参数
        body = CreateRecordSetRequestBody(
            name=DOMAIN_NAME + ".",
            type="CNAME",
            records=[CNAME_TARGET],
            ttl=300
        )
        # 再将 line 作为对象的属性来设置
        body.line = "default"
        
        request = CreateRecordSetRequest(zone_id=zone_id, body=body)
        dns_client.create_record_set(request)
        print(f"成功为 {DOMAIN_NAME} 创建了 CNAME 记录。")
        return True
    except exceptions.ClientRequestException as e:
        print(f"错误: 创建 CNAME 解析记录时失败: {e}")
        return False

def main():
    """主执行函数"""
    print("--- 开始更新华为云 CNAME 解析记录 (仅限全网默认线路) ---")
    
    if not all([DOMAIN_NAME]):
        print("错误: 缺少必要的 DOMAIN_NAME 环境变量。")
        return

    if not init_huawei_dns_client() or not get_zone_id():
        print("华为云客户端初始化或 Zone ID 获取失败，任务终止。")
        return

    existing_record = get_existing_cname_record()
    
    if existing_record:
        # 检查记录值是否已经是目标值
        if existing_record.records and existing_record.records[0] == CNAME_TARGET:
            print(f"\n记录已是最新，无需更新。当前指向: {CNAME_TARGET}")
            print("--- 任务完成 ---")
            return
        else:
            # 如果记录存在但值不正确，则删除
            print("\n--- 记录值不正确，开始删除旧记录 ---")
            delete_dns_record(existing_record.id, existing_record.records[0])
    else:
        print("\n无需删除旧记录。")

    print("\n--- 开始创建新的 CNAME 记录 ---")
    if create_cname_record():
        print(f"\n--- 更新完成 ---")
    else:
        print(f"\n--- 更新失败 ---")


if __name__ == '__main__':
    main()
