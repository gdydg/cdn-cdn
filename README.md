## 成果展示
这个吃API质量
<img src="https://freeimage.host/i/FpS21EP" alt="ikun" width=100% />



## 项目介绍

[项目地址](https://github.com/gdydg/cdn-cdn)

关于如何制作优选域名，网上已经有很多教程了，但是这些方法很多是有很高的限制性条件的，比如国内三网VPS,如何筛选合适的IP段等等。本项目完全不用考虑这些条件，只需利用华为云和大佬们优选IP的API，就能制作属于自己的优选域名。这里以优选cloudflare的A记录为例制作优选域名。

### 部署条件

- GitHub账号fork本项目。
- 华为云国际版账号。
- 优选IP的API(已内置微测网三网优化）。

### 部署步骤

- 到华为云国际版控制台`添加要优选的域名`——搜索`我的凭证`——创建访问密钥——回到保存项目id（到这里所有的变量值已经获得）。
- fork项目后点击`setting`，然后选择`secret and variables`,接下来配置变量。

- `HUAWEI_CLOUD_AK`
- `HUAWEI_CLOUD_SK`（以上两个是excel文件的密钥）
- `HUAWEI_CLOUD_PROJECT_ID`（项目id)
- `DOMAIN_NAME`
- `HUAWEI_CLOUD_ZONE_NAME`(如果你主域名在华为云，则第一个填主域名，第二个填子域名；如果是子域名，则两个都填你的子域名）

ok,变量配置成功，到action里面启动工作流，这样你的优选域名就制作成功了。

### 自定义选项

- 这里展示了A记录的添加，cname的方式只需到工作流文件修改最后一行的运行文件就行，update_ips1.py是全网默认A记录，update_ips2.py是三网优化A记录，update_ips3.py是全网默认cname记录，update_ips4.py是三网优化cname记录。（cron触发器设置也是在工作流文件）
- update_ips3.py和update_ips4.py里面优选cname的API脚本会从您指定的 API 地址获取内容，并将第一行作为 CNAME 的目标地址来进行后续的 DNS 更新操作。
- 可到py文件修改你的API和cname的优选域名，ttl,权重等等。
