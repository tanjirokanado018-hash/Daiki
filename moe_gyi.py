#!/usr/bin/env python3
import os
import re
import asyncio
import base64
import time
import subprocess
import aiohttp
from urllib.parse import urlparse, parse_qs, urljoin


# Terminal colors
bcyan = "\033[1;36m"
reset = "\033[0m"
white = "\033[0;37m"
bgreen = "\033[1;32m"
bred = "\033[1;31m"
yellow = "\033[0;33m"
g = "\033[1;32m"
r = "\033[1;31m"

TIMEOUT_SEC = 15

def show_banner():
    os.system('clear' if os.name == 'posix' else 'cls')
    print(f"{bcyan}="*55)
    print(f"   ⚡ RUIJIE PRO LOGIN  ⚡   ")
    print(f"   Myanmar Network Tool                              ")
    print(f"{bcyan}="*55 + f"{reset}")

class RuijiePro:
    def __init__(self):
        self.ip = None
        self.mac = None
        self.sid = None
        self.load_saved_ip()
        self.load_saved_mac()

    def load_saved_ip(self):
        if os.path.exists(".ip"):
            with open(".ip", "r") as f:
                self.ip = f.read().strip()

    def load_saved_mac(self):
        if os.path.exists(".mac"):
            with open(".mac", "r") as f:
                self.mac = f.read().strip()

    async def detect_gateway(self, session):
        """Detect gateway IP and MAC via connectivitycheck.gstatic.com"""
        print(f"\n{white}[*] Detecting gateway...{reset}")
        test_url = "http://connectivitycheck.gstatic.com/generate_204"
        headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14)'}
        try:
            async with session.get(test_url, headers=headers, timeout=5, allow_redirects=False) as resp:
                if resp.status in (301, 302):
                    location = resp.headers.get('Location', '')
                    parsed = urlparse(location)
                    qs = parse_qs(parsed.query)
                    if qs.get('gw_address'):
                        self.ip = qs['gw_address'][0]
                        with open(".ip", "w") as f:
                            f.write(self.ip)
                        print(f"{g}[+] Gateway IP: {self.ip}{reset}")
                    mac = qs.get('mac') or qs.get('umac') or qs.get('usermac')
                    if mac:
                        self.mac = mac[0]
                        with open(".mac", "w") as f:
                            f.write(self.mac)
                        print(f"{g}[+] MAC: {self.mac}{reset}")
                    return bool(self.ip)
                else:
                    # Use saved data if available
                    if self.ip and self.mac:
                        print(f"{g}[+] Using saved gateway info{reset}")
                        return True
                    print(f"{r}[-] Gateway detection failed{reset}")
                    return False
        except Exception as e:
            if self.ip and self.mac:
                print(f"{g}[+] Using saved gateway info (fallback){reset}")
                return True
            print(f"{r}[-] Gateway detection error: {e}{reset}")
            return False

    async def fetch_session_id(self, session):
        """Perform two-step redirect to obtain sessionId"""
        if not self.ip or not self.mac:
            return None
        step1_url = (
            f"https://portal-as.ruijienetworks.com/auth/wifidogAuth/login/"
            f"?gw_id=58b4bbe5d533&gw_sn=H1U50YX004340&gw_address=192.168.110.1"
            f"&gw_port=2060&ip={self.ip}&mac={self.mac}&slot_num=8&nasip=192.168.1.225"
            f"&ssid=VLAN233&ustate=0&mac_req=1&url=http%3A%2F%2F192.168.0.1%2F"
            f"&chap_id=%5C025&chap_challenge=%5C236%5C107%5C316%5C175%5C350%5C072%5C314%5C321%5C224%5C254%5C051%5C267%5C127%5C203%5C001%5C032"
        )
        headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14)'}
        try:
            async with session.get(step1_url, headers=headers, timeout=TIMEOUT_SEC) as r1:
                if r1.status != 200:
                    print(f"{r}[!] Step1 failed: HTTP {r1.status}{reset}")
                    return None
                body = await r1.text()
                match = re.search(r"self\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", body)
                if not match:
                    print(f"{r}[!] No redirect JS found{reset}")
                    return None
                step2_path = match.group(1)
                step2_url = urljoin("https://portal-as.ruijienetworks.com", step2_path)
            async with session.get(step2_url, headers=headers, timeout=TIMEOUT_SEC, allow_redirects=False) as r2:
                if r2.status != 302:
                    print(f"{r}[!] Step2 not a redirect (status {r2.status}){reset}")
                    return None
                location = r2.headers.get('Location', '')
                parsed = urlparse(location)
                sid_list = parse_qs(parsed.query).get('sessionId')
                if sid_list:
                    self.sid = sid_list[0]
                    print(f"{g}[+] Session ID: {self.sid[:16]}...{reset}")
                    return self.sid
                print(f"{r}[!] sessionId not found in redirect{reset}")
                return None
        except Exception as e:
            print(f"{r}[!] Session fetch error: {e}{reset}")
            return None

    async def handle_captcha(self, session):
        """Check CAPTCHA endpoint; if exists, show image and verify."""
        # Test endpoint with a GET request
        test_url = f"https://portal-as.ruijienetworks.com/api/auth/captcha/image?sessionId={self.sid}&_t={int(time.time()*1000)}"
        headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14)'}
        try:
            async with session.get(test_url, headers=headers) as resp:
                if resp.status == 404:
                    print(f"{yellow}[*] CAPTCHA not required, skipping.{reset}")
                    return "SKIP"
                elif resp.status != 200:
                    print(f"{yellow}[*] CAPTCHA endpoint returned {resp.status}, skipping.{reset}")
                    return "SKIP"
                # CAPTCHA exists → download image, show to user, verify
                img_data = await resp.read()
                temp_path = "/sdcard/temp_captcha.png"
                with open(temp_path, "wb") as f:
                    f.write(img_data)
                print(f"\n{yellow}📷 CAPTCHA image saved to {temp_path}{reset}")
                try:
                    subprocess.run(["chafa", temp_path], check=False)
                except FileNotFoundError:
                    print(f"{yellow}Install 'chafa' (pkg install chafa) for ASCII preview{reset}")
                user_input = input(f"{white}👉 Enter CAPTCHA code: {reset}").strip()
                if not user_input:
                    print(f"{r}[!] No input, aborting CAPTCHA{reset}")
                    return None
                # Verify
                verify_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/verify"
                payload = {"sessionId": self.sid, "authCode": user_input}
                async with session.post(verify_url, json=payload, headers=headers) as vresp:
                    if vresp.status == 200:
                        data = await vresp.json()
                        if data.get("success"):
                            print(f"{g}[+] CAPTCHA verified{reset}")
                            return user_input
                        else:
                            print(f"{r}[❌] Wrong CAPTCHA{reset}")
                            return None
                    else:
                        print(f"{r}[!] CAPTCHA verify failed (HTTP {vresp.status}){reset}")
                        return None
        except Exception as e:
            print(f"{r}[!] CAPTCHA error: {e}{reset}")
            return "SKIP"   # Assume not required on error

    async def submit_voucher(self, session, voucher, captcha_code, debug=False):
        """Send voucher + optional captcha to /api/auth/voucher/"""
        if not self.sid:
            if not await self.fetch_session_id(session):
                return False
        api_url = base64.b64decode(
            b'aHR0cHM6Ly9wb3J0YWwtYXMucnVpamllbmV0d29ya3MuY29tL2FwaS9hdXRoL3ZvdWNoZXIvP2xhbmc9ZW5fVVM='
        ).decode()
        payload = {"accessCode": voucher, "sessionId": self.sid, "apiVersion": 1}
        if captcha_code and captcha_code != "SKIP":
            payload["captcha"] = captcha_code   # or "authCode"? test both; most use "captcha"
        headers = {
            "authority": "portal-as.ruijienetworks.com",
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://portal-as.ruijienetworks.com",
            "referer": f"https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?sessionId={self.sid}",
            "user-agent": "Mozilla/5.0 (Linux; Android 12)",
        }
        try:
            async with session.post(api_url, json=payload, headers=headers) as resp:
                text = await resp.text()
                if debug:
                    print(f"{yellow}[DEBUG] Voucher response: {text[:300]}{reset}")
                if 'logonUrl' in text:
                    print(f"{g}✅ Voucher '{voucher}' accepted!{reset}")
                    return True
                else:
                    print(f"{r}❌ Voucher rejected.{reset}")
                    return False
        except Exception as e:
            if debug:
                print(f"{r}[!] Voucher error: {e}{reset}")
            return False

    async def activate_internet(self, session):
        """Final POST to http://{ip}:2060/wifidog/auth to get internet access."""
        if not self.sid:
            if not await self.fetch_session_id(session):
                return False
        url = f"http://{self.ip}:2060/wifidog/auth"
        params = {"token": self.sid, "phoneNumber": "12345678901"}
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with session.post(url, params=params, headers=headers, timeout=TIMEOUT_SEC) as resp:
                if resp.status == 200:
                    print(f"{g}✅ Internet activated successfully!{reset}")
                    return True
                else:
                    print(f"{r}⚠️ Activation failed (HTTP {resp.status}){reset}")
                    return False
        except Exception as e:
            print(f"{r}[!] Activation error: {e}{reset}")
            return False

    async def run(self, voucher, debug=False):
        print(f"\n{white}[ * ] Starting Ruijie Pro flow...{reset}")
        async with aiohttp.ClientSession() as session:
            if not await self.detect_gateway(session):
                print(f"{r}[!] Gateway detection failed{reset}")
                return
            if not await self.fetch_session_id(session):
                print(f"{r}[!] Could not obtain session ID{reset}")
                return

            captcha = await self.handle_captcha(session)
            if captcha is None:
                print(f"{r}[!] CAPTCHA required but verification failed{reset}")
                return

            if await self.submit_voucher(session, voucher, captcha, debug):
                await self.activate_internet(session)
            else:
                print(f"{r}[!] Voucher authentication failed.{reset}")

async def main():
    show_banner()
    voucher = input(f"\n{yellow}👉 Enter Voucher Code: {reset}").strip()
    if not voucher:
        print(f"{r}[!] No voucher provided.{reset}")
        return
    client = RuijiePro()
    await client.run(voucher, debug=True)
    input(f"\n{white}Press Enter to exit...{reset}")

if __name__ == "__main__":
    asyncio.run(main())