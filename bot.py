import base64
import hashlib
import hmac
import time
import json
from urllib import parse
import yaml
import requests
import smtplib
import subprocess
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
from pyrate_limiter import Duration, Limiter, Rate
from utils import Color

__all__ = ["feishuBot", "wecomBot", "dingtalkBot", "qqBot", "mailBot"]
today = datetime.now().strftime("%Y-%m-%d")


class feishuBot:
    """Feishu Bot for sending feed updates"""
    def __init__(self, key, proxy_url='') -> None:
        self.key = key
        self.proxy = {'http': proxy_url, 'https': proxy_url} if proxy_url else {'http': None, 'https': None}

    @staticmethod
    def parse_results(results: list):
        text_list = []
        for result in results:
            (feed, value), = result.items()
            text = f'[ {feed} ]\n\n'
            for title, link in value.items():
                text += f'{title}\n{link}\n\n'
            text_list.append(text.strip())
        return text_list

    def send(self, text_list: list):
        for text in text_list:
            print(f'{len(text)} {text[:50]}...{text[-50:]}')
            data = {"msg_type": "text", "content": {"text": text}}
            headers = {'Content-Type': 'application/json'}
            url = f'https://open.feishu.cn/open-apis/bot/v2/hook/{self.key}'
            r = requests.post(url=url, headers=headers, data=json.dumps(data), proxies=self.proxy)

            if r.status_code == 200:
                Color.print_success('[+] feishuBot sent success')
            else:
                Color.print_failed('[-] feishuBot sent failed')
                print(r.text)

    def send_markdown(self, text):
        data = {"msg_type": "text", "content": {"text": text}}
        self.send([data])


class wecomBot:
    """WeCom Bot for sending feed updates"""
    def __init__(self, key, proxy_url='') -> None:
        self.key = key
        self.proxy = {'http': proxy_url, 'https': proxy_url} if proxy_url else {'http': None, 'https': None}

    @staticmethod
    def parse_results(results: list):
        text_list = []
        for result in results:
            (feed, value), = result.items()
            text = f'## {feed}\n'
            for title, link in value.items():
                text += f'- [{title}]({link})\n'
            text_list.append(text.strip())
        return text_list

    def send(self, text_list: list):
        limiter = Limiter(Rate(20, Duration.MINUTE))     # Rate limit, 20/min
        for text in text_list:
            with limiter.ratelimit('identity', delay=True):
                print(f'{len(text)} {text[:50]}...{text[-50:]}')

                data = {"msgtype": "markdown", "markdown": {"content": text}}
                headers = {'Content-Type': 'application/json'}
                url = f'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self.key}'
                r = requests.post(url=url, headers=headers, data=json.dumps(data), proxies=self.proxy)

                if r.status_code == 200:
                    Color.print_success('[+] wecomBot sent success')
                else:
                    Color.print_failed('[-] wecomBot sent failed')
                    print(r.text)


class dingtalkBot:
    """DingTalk Bot for sending feed updates"""
    def __init__(self, key, secret, proxy_url='') -> None:
        self.key = key
        self.secret = secret
        self.proxy = {'http': proxy_url, 'https': proxy_url} if proxy_url else {'http': None, 'https': None}

    @staticmethod
    def parse_results(results: dict):
        text_list = []
        for result in results.items():
            feed, value = result
            text = f"{feed}:\n" + ''.join(f'- [{title}]({link})\n' for title, link in value.items())
            text_list.append(text.strip())
        return text_list

    def send(self, text_list: list):
        # DingTalk uses similar logic to WeCom but might not need limiter strictly
        # Reusing logic from WeCom or simplifying
        for text in text_list:
            print(f'{len(text)} {text[:50]}...{text[-50:]}')
            data = {"text": text}
            headers = {'Content-Type': 'application/json'}
            url = f'https://oapi.dingtalk.com/robot/send?access_token={self.key}'
            r = requests.post(url=url, headers=headers, data=json.dumps(data), proxies=self.proxy)

            if r.status_code == 200:
                Color.print_success('[+] dingtalkBot sent success')
            else:
                Color.print_failed('[-] dingtalkBot sent failed')
                print(r.text)


class qqBot:
    """QQ Bot Stub"""
    def __init__(self, key):
        self.key = key

    @staticmethod
    def parse_results(results: list):
        return results

    def send(self, text_list):
        return text_list


class mailBot:
    """Mail Bot Stub"""
    def __init__(self, smtp, user, password):
        self.smtp = smtp
        self.user = user
        self.password = password

    def send(self, text):
        msg = MIMEText(text)
        msg['Subject'] = 'Daily Feed'
        msg['From'] = self.user
        msg['To'] = self.user
        s = smtplib.SMTP(self.smtp)
        s.login(self.user, self.password)
        s.sendmessage(msg)
        s.quit()