import os
import pprint
import subprocess

from colorama import Fore


class Color:
    @staticmethod
    def print_focus(data: str):
        print(Fore.YELLOW+data+Fore.RESET)

    @staticmethod
    def print_success(data: str):
        print(Fore.LIGHTGREEN_EX+data+Fore.RESET)

    @staticmethod
    def print_failed(data: str):
        print(Fore.LIGHTRED_EX+data+Fore.RESET)

    @staticmethod
    def print(data):
        pprint.pprint(data)


class Pattern:
    @staticmethod
    def create(length: int=8192):
        pattern = ''
        parts = ['A', 'a', '0']
        while len(pattern) != length:
            pattern += parts[len(pattern) % 3]
            if len(pattern) % 3 == 0:
                parts[2] = chr(ord(parts[2]) + 1)
                if parts[2] > '9':
                    parts[2] = '0'
                    parts[1] = chr(ord(parts[1]) + 1)
                    if parts[1] > 'z':
                        parts[1] = 'a'
                        parts[0] = chr(ord(parts[0]) + 1)
                        if parts[0] > 'Z':
                            parts[0] = 'A'
        return pattern

    @staticmethod
    def offset(value: str, length: int=8192):
        return Pattern.create(length).index(value)


def popen(cmd:str) -> str:
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True).stdout as source:
        return source.read().decode(encoding="utf-8")


def getenv(key_name, pick=False):
    if pick:
        return os.getenv("PICKER_"+key_name)
    else:
        return os.getenv(key_name)
