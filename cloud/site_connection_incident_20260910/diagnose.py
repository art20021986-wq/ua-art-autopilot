"""Read-only public UA ART DNS/TLS/HTTP incident probe; never reloads anything."""
import concurrent.futures
import datetime
import json
import socket
import ssl
import subprocess
import time
from pathlib import Path

HOSTS = ('uaart.com.ua', 'www.uaart.com.ua')
URLS = ('http://uaart.com.ua/', 'http://www.uaart.com.ua/',
        'https://uaart.com.ua/', 'https://www.uaart.com.ua/',
        'https://www.uaart.com.ua/video/index.html',
        'https://www.uaart.com.ua/video/katalog.html')
UA = {
    'default': 'UA-ART-incident-diagnostic/1',
    'iphone_chrome': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/128.0.0.0 Mobile/15E148 Safari/604.1',
    'iphone_webview': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
}

def command(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=50)
        return {'exit_code': r.returncode, 'stdout': r.stdout[-10000:], 'stderr': r.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {'error': 'COMMAND_TIMEOUT'}

def dns(host):
    return {'host': host, 'records': {kind:command(['dig', '+time=3', '+tries=1', host, kind]) for kind in ('A','AAAA','CNAME')}}

def tls(host):
    results=[]
    seen=set()
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError as exc:
        return {'host':host,'error':str(exc)}
    for family,kind,proto,_,addr in addresses:
        if addr[0] in seen:
            continue
        seen.add(addr[0])
        item={'ip':addr[0],'family':family}
        start=time.monotonic()
        try:
            with socket.socket(family,kind,proto) as raw:
                raw.settimeout(15)
                raw.connect(addr)
                with ssl.create_default_context().wrap_socket(raw,server_hostname=host) as sock:
                    cert=sock.getpeercert()
                    item.update(tls_version=sock.version(),cipher=sock.cipher(),
                                not_before=cert.get('notBefore'),not_after=cert.get('notAfter'),
                                subject_alt_name=cert.get('subjectAltName'),issuer=cert.get('issuer'),verified=True)
        except Exception as exc:
            item.update(verified=False,error=type(exc).__name__+': '+str(exc))
        item['seconds']=round(time.monotonic()-start,3)
        results.append(item)
    return {'host':host,'addresses':results}

def http(url,agent,family):
    nonce=str(time.time_ns())
    result=command(['curl', family, '--silent','--show-error','--location',
                    '--proto','=http,https','--proto-redir','=http,https','--max-redirs','5',
                    '--connect-timeout','10','--max-time','25','--max-filesize','10485760',
                    '--user-agent',UA[agent], '--header','Cache-Control: no-cache',
                    '--output','/dev/null','--dump-header','-', '--write-out',
                    '\nMETRICS http=%{http_code} remote_ip=%{remote_ip} final=%{url_effective} dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total} verify=%{ssl_verify_result}\n',
                    url+'?incident_probe='+nonce])
    return {'url':url,'agent':agent,'family':family,**result}

def main():
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        dns_jobs=[pool.submit(dns,h) for h in HOSTS]
        tls_jobs=[pool.submit(tls,h) for h in HOSTS]
        http_jobs=[pool.submit(http,u,a,f) for u in URLS for a,f in
                   [('default','-4'),('iphone_chrome','-4'),('iphone_webview','-4'),('default','-6')]]
        result={'started_at':start,'production_write':False,
                'limitations':['HTTP user-agent checks do not reproduce an actual iPhone or TikTok browser.',
                               'IPv6 failure may reflect runner connectivity; compare with DNS AAAA records.',
                               'No blocked server logs accessed.'],
                'dns':[j.result() for j in dns_jobs], 'tls':[j.result() for j in tls_jobs],
                'http':[j.result() for j in http_jobs]}
    result['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    Path('incident-connection-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    main()
