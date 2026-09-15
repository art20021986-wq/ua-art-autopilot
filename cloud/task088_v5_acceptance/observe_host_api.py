"""GET-only hosting observation with the existing provider-managed API_TOKEN.

The provider documents this variable in https://help.pythonanywhere.com/pages/API/.
No token is printed, exported, persisted, created, or transmitted outside its
existing PythonAnywhere account. No new permissions or API writes occur.
"""
import datetime
import json
import os
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('HOSTING_REDIRECT_FORBIDDEN')


def main():
    token = os.environ.get('API_TOKEN', '')
    result = {'kind': 'READ_ONLY_HOSTING_API_OBSERVATION',
              'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'existing_api_token_present': bool(token), 'production_written': False}
    if token:
        base = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
        opener = urllib.request.build_opener(NoRedirect())
        for key, endpoint in (
            ('static_mappings', 'webapps/www.uaart.com.ua/static_files/'),
            ('webapps', 'webapps/'), ('always_on', 'always_on/')):
            try:
                request = urllib.request.Request(base + endpoint,
                    headers={'Authorization': 'Token ' + token}, method='GET')
                with opener.open(request, timeout=20) as response:
                    data = json.loads(response.read(1024 * 1024))
                if type(data) is not list:
                    raise ValueError('EXPECTED_LIST_RESPONSE')
                if key == 'static_mappings':
                    result[key] = [{k: item[k] for k in ('id', 'url', 'path') if k in item} for item in data]
                elif key == 'webapps':
                    result[key] = [{k: item[k] for k in ('domain_name', 'python_version', 'enabled') if k in item} for item in data]
                else:
                    result[key] = [{'id': item.get('id'), 'enabled': item.get('enabled'),
                        'running': item.get('running'), 'state': item.get('state'), 'status': item.get('status'),
                        'is_crm': '/home/Carix/start_safe.py' in str(item.get('command', ''))}
                        for item in data]
            except Exception as error:
                result[key] = {'error_type': type(error).__name__,
                               'http_status': getattr(error, 'code', None)}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
