import json
import subprocess
import logging
import csv
import socket
from tencentcloud.common import credential
from tencentcloud.dnspod.v20210323 import dnspod_client, models
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

# 配置日志
logging.basicConfig(filename='update_dns.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("脚本开始运行")

# 读取配置文件
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    logging.info("配置文件读取成功")
except Exception as e:
    logging.error("读取配置文件失败: %s", e)
    exit(1)

domain = config['domain']
dnspod_secretid = config['dnspod_secretid']
dnspod_secretkey = config['dnspod_secretkey']
modify_a_record = config['modify_a_record']
modify_aaaa_record = config['modify_aaaa_record']
a_record_line = config.get('a_record_line', '默认')
aaaa_record_line = config.get('aaaa_record_line', '默认')
ipv4_method = config.get('ipv4_method', 1)  # 默认使用方法1
ipv4_domain = config.get('ipv4_domain', 'visa.cn')  # 默认域名

# 初始化腾讯云DNSPod客户端
try:
    cred = credential.Credential(dnspod_secretid, dnspod_secretkey)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "dnspod.tencentcloudapi.com"
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    client = dnspod_client.DnspodClient(cred, "", clientProfile)
    logging.info("DNSPod客户端初始化成功")
except Exception as e:
    logging.error("DNSPod客户端初始化失败: %s", e)
    exit(1)

# 获取所有主域名
def get_all_main_domains():
    try:
        req = models.DescribeDomainListRequest()
        params = {}
        req.from_json_string(json.dumps(params))
        resp = client.DescribeDomainList(req)
        logging.debug("DescribeDomainList 响应: %s", resp.to_json_string())
        main_domains = [domain.Name for domain in resp.DomainList]
        return main_domains
    except Exception as e:
        logging.error("获取主域名列表失败: %s", e)
        return []

# 解析域名，确定主域名和子域名
def parse_domain(domain, main_domains):
    for main_domain in main_domains:
        if domain.endswith(main_domain):
            sub_domain = domain[:-len(main_domain)].rstrip('.')
            if not sub_domain:
                sub_domain = '@'
            return main_domain, sub_domain
    return None, None

main_domains = get_all_main_domains()
main_domain, sub_domain = parse_domain(domain, main_domains)
if not main_domain:
    logging.error("未能匹配到主域名")
    exit(1)

logging.info("解析域名结果: 主域名=%s, 子域名=%s", main_domain, sub_domain)

# 获取最快的IPv6地址
def get_fastest_ipv6():
    try:
        logging.info("开始获取最快IPv6地址")
        result = subprocess.run(['./CloudflareST', '-f', 'ipv6.txt', '-n', '800', '-o', 'result.csv', '-t', '6', '-dn', '3'], capture_output=True, text=True, timeout=600)
        logging.debug("CloudflareST 返回码: %s", result.returncode)
        logging.debug("CloudflareST 输出: %s", result.stdout)
        logging.debug("CloudflareST 错误输出: %s", result.stderr)
        
        # 读取result.csv文件
        with open('result.csv', 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # 跳过表头
            first_row = next(reader)  # 读取第一行
            ipv6_address = first_row[0]
            logging.info("获取到的最快IPv6地址: %s", ipv6_address)
            return ipv6_address
    except subprocess.TimeoutExpired:
        logging.error("获取最快IPv6地址超时")
    except Exception as e:
        logging.error("获取最快IPv6地址失败: %s", e)
    return None

# 获取最快的IPv4地址
def get_fastest_ipv4():
    try:
        logging.info("开始获取最快IPv4地址")
        result = subprocess.run(['./CloudflareST', '-f', 'ip.txt', '-n', '800', '-o', 'result_ipv4.csv', '-t', '4', '-dn', '3'], capture_output=True, text=True, timeout=600)
        logging.debug("CloudflareST 返回码: %s", result.returncode)
        logging.debug("CloudflareST 输出: %s", result.stdout)
        logging.debug("CloudflareST 错误输出: %s", result.stderr)
        
        # 读取result_ipv4.csv文件
        with open('result_ipv4.csv', 'r') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # 跳过表头
            first_row = next(reader)  # 读取第一行
            ipv4_address = first_row[0]
            logging.info("获取到的最快IPv4地址: %s", ipv4_address)
            return ipv4_address
    except subprocess.TimeoutExpired:
        logging.error("获取最快IPv4地址超时")
    except Exception as e:
        logging.error("获取最快IPv4地址失败: %s", e)
    return None

# 获取visa.cn的IPv4地址
def get_visa_ipv4():
    try:
        logging.info("开始获取 %s 的IPv4地址", ipv4_domain)
        ipv4_address = socket.gethostbyname(ipv4_domain)
        logging.info("获取到的 %s 的IPv4地址: %s", ipv4_domain, ipv4_address)
        return ipv4_address
    except Exception as e:
        logging.error("获取 %s 的IPv4地址失败: %s", ipv4_domain, e)
    return None

# 根据配置选择获取IPv4地址的方法
if ipv4_method == 1:
    ipv4_address = get_visa_ipv4()
else:
    ipv4_address = get_fastest_ipv4()

if not ipv4_address:
    logging.error("未能获取IPv4地址")
    exit(1)

# 获取记录ID
def get_record_id(record_type, record_line):
    try:
        req = models.DescribeRecordListRequest()
        params = {
            "Domain": main_domain,
            "Subdomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": record_line,
            "Action": "DescribeRecordList",
            "Version": "2021-03-23"
        }
        req.from_json_string(json.dumps(params))
        resp = client.DescribeRecordList(req)
        logging.debug("DescribeRecordList 响应: %s", resp.to_json_string())
        for record in resp.RecordList:
            if record.Type == record_type and record.Name == sub_domain and record.Line == record_line:
                return record.RecordId
    except Exception as e:
        logging.error("获取记录ID失败: %s", e)
    return None

# 修改DNSPod记录
def modify_record(record_type, ip, record_line):
    record_id = get_record_id(record_type, record_line)
    if not record_id:
        logging.warning(f"未找到{record_type}记录")
        return

    try:
        req = models.ModifyRecordRequest()
        params = {
            "Domain": main_domain,
            "RecordId": record_id,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": record_line,
            "Value": ip,
            "Action": "ModifyRecord",
            "Version": "2021-03-23"
        }
        req.from_json_string(json.dumps(params))
        resp = client.ModifyRecord(req)
        logging.debug("ModifyRecord 响应: %s", resp.to_json_string())
        return resp.to_json_string()
    except Exception as e:
        logging.error("修改记录失败: %s", e)
        return None

# 创建DNSPod记录
def create_record(record_type, ip, record_line):
    try:
        req = models.CreateRecordRequest()
        params = {
            "Domain": main_domain,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": record_line,
            "Value": ip,
            "Action": "CreateRecord",
            "Version": "2021-03-23"
        }
        req.from_json_string(json.dumps(params))
        resp = client.CreateRecord(req)
        logging.debug("CreateRecord 响应: %s",