# -*- coding: utf-8 -*-

# 打卡脚本修改自ZJU-nCov-Hitcarder的开源代码，感谢这位同学开源的代码
# 更新版本：适配浙大认证系统可能的页面变化

import requests
import json
import re
import datetime
import time
import sys
from bs4 import BeautifulSoup


class DaKa(object):
    """Hit card class

    Attributes:
        username: (str) 浙大统一认证平台用户名（一般为学号）
        password: (str) 浙大统一认证平台密码
        login_url: (str) 登录url
        base_url: (str) 打卡首页url
        save_url: (str) 提交打卡url
        self.headers: (dir) 请求头
        sess: (requests.Session) 统一的session
    """

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.login_url = "https://zjuam.zju.edu.cn/cas/login?service=https%3A%2F%2Fhealthreport.zju.edu.cn%2Fa_zju%2Fapi%2Fsso%2Findex%3Fredirect%3Dhttps%253A%252F%252Fhealthreport.zju.edu.cn%252Fncov%252Fwap%252Fdefault%252Findex"
        self.base_url = "https://healthreport.zju.edu.cn/ncov/wap/default/index"
        self.save_url = "https://healthreport.zju.edu.cn/ncov/wap/default/save"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.sess = requests.Session()

    def _safe_regex_search(self, patterns, text, field_name):
        """安全地搜索正则表达式，支持多种模式"""
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                print(f"✅ 使用模式 {i+1} 找到{field_name}: {match.group(1)[:30]}...")
                return match.group(1)
        
        print(f"❌ 所有模式都无法匹配{field_name}")
        return None

    def _check_page_status(self, response):
        """检查页面状态，提供调试信息"""
        print(f"📊 响应状态码: {response.status_code}")
        print(f"🎯 最终URL: {response.url}")
        
        # 保存调试信息
        with open('debug_login_page.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("💾 已保存登录页面到 debug_login_page.html")
        
        # 检查常见情况
        page_lower = response.text.lower()
        checks = [
            ('验证码', 'captcha'),
            ('维护', 'maintenance'),
            ('error', 'error'),
            ('denied', 'denied'),
            ('unavailable', 'unavailable')
        ]
        
        detected_issues = []
        for chinese, english in checks:
            if chinese in response.text or english in page_lower:
                detected_issues.append(chinese if chinese in response.text else english)
        
        if detected_issues:
            print(f"⚠️  检测到页面问题: {', '.join(detected_issues)}")
        
        return detected_issues

    def login(self):
        """Login to ZJU platform"""
        print("🌐 正在访问登录页面...")
        res = self.sess.get(self.login_url, headers=self.headers)
        
        # 检查页面状态
        issues = self._check_page_status(res)
        
        # 如果检测到严重问题，提前退出
        if any(issue in ['维护', 'error', 'denied', 'unavailable'] for issue in issues):
            raise LoginError(f'登录页面异常: {", ".join(issues)}')
        
        # 检查验证码
        if '验证码' in res.text or 'captcha' in res.text.lower():
            print("🚫 检测到验证码要求，当前脚本不支持验证码处理")
            print("💡 建议：请手动完成今日打卡，或等待脚本更新支持验证码")
            raise LoginError('登录需要验证码，脚本暂不支持')
        
        # 多种模式匹配execution字段
        execution_patterns = [
            r'name\s*=\s*"execution"\s*value\s*=\s*"([^"]*)"',
            r'name\s*=\s*\'execution\'\s*value\s*=\s*\'([^\']*)\'',
            r'name="lt"\s*value="([^"]*)"',
            r'name=\'lt\'\s*value=\'([^\']*)\'',
            r'execution"\s*:\s*"([^"]*)"',
            r'execution.*?value="([^"]*)"',
            r'<input[^>]*name="execution"[^>]*value="([^"]*)"',
            r'<input[^>]*name=\'execution\'[^>]*value=\'([^\']*)\''
        ]
        
        execution = self._safe_regex_search(execution_patterns, res.text, "execution字段")
        
        if not execution:
            # 使用BeautifulSoup作为备选方案
            print("🔄 尝试使用BeautifulSoup解析...")
            try:
                soup = BeautifulSoup(res.text, 'html.parser')
                execution_input = (soup.find('input', {'name': 'execution'}) or 
                                 soup.find('input', {'name': 'lt'}))
                if execution_input and execution_input.get('value'):
                    execution = execution_input.get('value')
                    print(f"✅ BeautifulSoup找到字段: {execution[:30]}...")
                else:
                    print("❌ BeautifulSoup也未找到相关字段")
                    
                    # 输出页面中所有input字段名用于调试
                    print("📋 页面中的input字段:")
                    inputs = soup.find_all('input', {'name': True})
                    for inp in inputs[:15]:  # 显示前15个
                        name = inp.get('name')
                        value = inp.get('value', 'N/A')
                        if len(str(value)) > 50:
                            value = str(value)[:50] + "..."
                        print(f"   - {name}: {value}")
                    
                    raise LoginError('无法提取登录所需字段，页面结构可能已重大变化')
            except Exception as e:
                print(f"❌ BeautifulSoup解析失败: {e}")
                raise LoginError('页面解析失败，请检查网络连接或页面结构')
        
        # 获取RSA公钥
        print("🔑 获取加密公钥...")
        try:
            pubkey_res = self.sess.get(
                url='https://zjuam.zju.edu.cn/cas/v2/getPubKey', 
                headers=self.headers
            )
            
            if pubkey_res.status_code != 200:
                raise LoginError(f'获取公钥失败，状态码: {pubkey_res.status_code}')
                
            pubkey_data = pubkey_res.json()
            n, e = pubkey_data['modulus'], pubkey_data['exponent']
            print("✅ 成功获取RSA公钥")
        except Exception as e:
            print(f"❌ 获取公钥失败: {e}")
            raise LoginError('无法获取加密公钥，请检查网络连接')
        
        # 加密密码
        encrypt_password = self._rsa_encrypt(self.password, e, n)

        # 构建登录数据
        data = {
            'username': self.username,
            'password': encrypt_password,
            'execution': execution,
            '_eventId': 'submit'
        }
        
        print("🔐 提交登录信息...")
        res = self.sess.post(url=self.login_url, data=data, headers=self.headers)

        # 检查登录是否成功
        response_text = res.content.decode('utf-8', errors='ignore')
        if '统一身份认证' in response_text or 'cas' in response_text.lower():
            print("❌ 登录失败，可能原因：")
            print("   - 用户名或密码错误")
            print("   - 账户被锁定")
            print("   - 系统拒绝登录")
            raise LoginError('登录失败，请核实账号密码重新登录')
        
        print("✅ 登录成功！")
        return self.sess

    def post(self):
        """Post the hitcard info"""
        print("📤 提交打卡信息...")
        res = self.sess.post(self.save_url, data=self.info, headers=self.headers)
        response_data = json.loads(res.text)
        print(f"📬 服务器响应: {response_data}")
        return response_data

    def get_date(self):
        """Get current date"""
        today = datetime.date.today()
        return "%4d%02d%02d" % (today.year, today.month, today.day)

    def get_info(self, html=None):
        """Get hitcard info, which is the old info with updated new time."""
        if not html:
            print("🌐 获取个人信息页面...")
            res = self.sess.get(self.base_url, headers=self.headers)
            html = res.content.decode('utf-8', errors='ignore')

        try:
            # 多种方式匹配oldInfo
            old_info_patterns = [
                r'oldInfo: ({[^\n]+})',
                r'oldInfo\s*:\s*({[^\n]+})',
                r'var oldInfo\s*=\s*({[^\n]+})'
            ]
            
            old_infos = []
            for pattern in old_info_patterns:
                matches = re.findall(pattern, html)
                old_infos.extend(matches)
            
            if len(old_infos) != 0:
                old_info = json.loads(old_infos[0])
                print("✅ 成功解析缓存信息")
            else:
                raise RegexMatchError("未发现缓存信息，请先至少手动成功打卡一次再运行脚本")

            # 匹配def信息
            def_patterns = [
                r'def = ({[^\n]+})',
                r'def\s*=\s*({[^\n]+})',
                r'var def\s*=\s*({[^\n]+})'
            ]
            
            def_matches = []
            for pattern in def_patterns:
                matches = re.findall(pattern, html)
                def_matches.extend(matches)
                
            if def_matches:
                new_info_tmp = json.loads(def_matches[0])
                new_id = new_info_tmp['id']
            else:
                raise RegexMatchError("无法找到def信息")

            # 匹配姓名
            name_patterns = [
                r'realname: "([^\"]+)",',
                r'realname\s*:\s*"([^"]+)"',
                r'"realname"\s*:\s*"([^"]+)"'
            ]
            name_match = self._safe_regex_search(name_patterns, html, "姓名")
            if not name_match:
                raise RegexMatchError("无法找到姓名信息")

            # 匹配学号
            number_patterns = [
                r"number: '([^\']+)',",
                r"number\s*:\s*'([^\']+)'",
                r"'number'\s*:\s*'([^\']+)'"
            ]
            number_match = self._safe_regex_search(number_patterns, html, "学号")
            if not number_match:
                raise RegexMatchError("无法找到学号信息")

        except IndexError:
            raise RegexMatchError('Relative info not found in html with regex')
        except json.decoder.JSONDecodeError as e:
            print(f"❌ JSON解析失败: {e}")
            print("📋 问题数据:", old_infos[0][:200] if old_infos else "N/A")
            raise DecodeError('JSON decode error')

        new_info = old_info.copy()
        new_info['id'] = new_id
        new_info['name'] = name_match
        new_info['number'] = number_match
        new_info["date"] = self.get_date()
        new_info["created"] = round(time.time())
        new_info["address"] = "浙江省杭州市西湖区"
        new_info["area"] = "浙江省 杭州市 西湖区"
        new_info["province"] = new_info["area"].split(' ')[0]
        new_info["city"] = new_info["area"].split(' ')[1]
        # form change
        new_info['jrdqtlqk[]'] = 0
        new_info['jrdqjcqk[]'] = 0
        new_info['sfsqhzjkk'] = 1   # 是否申领杭州健康码
        new_info['sqhzjkkys'] = 1   # 杭州健康吗颜色，1:绿色 2:红色 3:黄色
        new_info['sfqrxxss'] = 1    # 是否确认信息属实
        new_info['jcqzrq'] = ""
        new_info['gwszdd'] = ""
        new_info['szgjcs'] = ""
        self.info = new_info
        
        print("✅ 个人信息准备完成")
        return new_info

    def _rsa_encrypt(self, password_str, e_str, M_str):
        """RSA加密密码"""
        try:
            password_bytes = bytes(password_str, 'ascii')
            password_int = int.from_bytes(password_bytes, 'big')
            e_int = int(e_str, 16)
            M_int = int(M_str, 16)
            result_int = pow(password_int, e_int, M_int)
            return hex(result_int)[2:].rjust(128, '0')
        except Exception as e:
            raise Exception(f"RSA加密失败: {e}")


# Exceptions
class LoginError(Exception):
    """Login Exception"""
    pass


class RegexMatchError(Exception):
    """Regex Matching Exception"""
    pass


class DecodeError(Exception):
    """JSON Decode Exception"""
    pass


def main(username, password):
    """Hit card process"""

    print("\n" + "="*50)
    print("[Time] %s" % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("🚌 浙大自动打卡脚本启动")
    print(f"👤 用户: {username}")
    print("="*50)

    dk = DaKa(username, password)

    print("\n🔐 步骤1: 登录认证")
    try:
        dk.login()
        print("✅ 登录步骤完成\n")
    except Exception as err:
        print(f"❌ 登录失败: {err}")
        print("\n💡 故障排除建议:")
        print("1. 检查用户名和密码是否正确")
        print("2. 检查网络连接是否正常")
        print("3. 查看 debug_login_page.html 了解页面结构")
        print("4. 浙大认证系统可能已更新，请关注脚本更新")
        raise Exception

    print("📋 步骤2: 获取个人信息")
    try:
        dk.get_info()
        print("✅ 信息获取完成\n")
    except Exception as err:
        print(f'❌ 获取信息失败: {err}')
        print("💡 请确保已经至少手动成功打卡过一次")
        raise Exception

    print("📝 步骤3: 提交打卡")
    try:
        res = dk.post()
        if str(res['e']) == '0':
            print('🎉 打卡成功！今日已完成健康打卡')
        else:
            print(f'⚠️  打卡异常: {res["m"]}')
            print("💡 请检查打卡结果或手动确认")
    except Exception as e:
        print(f'❌ 数据提交失败: {e}')
        raise Exception

    print("\n" + "="*50)
    print("✨ 脚本执行完毕")
    print("="*50)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("使用方法: python3 clock-in.py <用户名> <密码>")
        print("示例: python3 clock-in.py 123456789 zjupassword")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if not username or not password:
        print("❌ 用户名和密码不能为空")
        sys.exit(1)
    
    try:
        main(username, password)
    except Exception as e:
        print(f"\n💥 脚本执行失败: {e}")
        print("📞 如需帮助，请查看错误信息并联系开发者")
        exit(1)
