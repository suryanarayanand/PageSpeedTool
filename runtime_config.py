"""Runtime settings; credentials are supplied through the hosting environment."""
import os


def boolean_setting(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError(name + ' must be true or false')


def server_settings():
    cloud = boolean_setting('PAGESPEED_CLOUD')
    hosts = {value.strip().lower() for value in os.getenv('PAGESPEED_ALLOWED_HOSTS', 'localhost,127.0.0.1,::1').split(',') if value.strip()}
    if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
        hosts.add(os.environ['RENDER_EXTERNAL_HOSTNAME'].lower())
    return {
        'CLOUD_MODE': cloud,
        'PUBLIC_REPORTS': boolean_setting('PAGESPEED_PUBLIC_REPORTS', cloud),
        'REQUIRE_HTTPS': boolean_setting('PAGESPEED_REQUIRE_HTTPS', cloud),
        'ALLOWED_REPORT_HOSTS': hosts,
        'ADMIN_USERNAME': os.getenv('PAGESPEED_ADMIN_USERNAME', ''),
        'ADMIN_PASSWORD': os.getenv('PAGESPEED_ADMIN_PASSWORD', ''),
        'ALLOW_BROWSER': boolean_setting('PAGESPEED_ALLOW_BROWSER', not cloud),
    }


def configuration_error(config):
    if config['CLOUD_MODE'] and (not config['ADMIN_USERNAME'] or not config['ADMIN_PASSWORD']):
        return 'Cloud hosting requires PAGESPEED_ADMIN_USERNAME and PAGESPEED_ADMIN_PASSWORD.'
    return None
