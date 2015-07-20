# Add the App Engine SDK's bundled libraries (django, webob, yaml, etc.) to
# sys.path so we can use them instead of adding them all to tests_require in
# setup.py.
# https://cloud.google.com/appengine/docs/python/tools/localunittesting#Python_Setting_up_a_testing_framework
import dev_appserver
dev_appserver.fix_sys_path()

# Also use the App Engine SDK's mox because it has bug fixes that aren't in pypi
# 0.5.3. (Annoyingly, they both say they're version 0.5.3.)
import os, sys
sys.path.append(os.path.join(dev_appserver._DIR_PATH, 'lib', 'mox'))

# Show logging when running individual test modules, methods, etc; suppress it
# when running all tests.
import logging
if 'discover' in sys.argv:
  logging.disable(logging.CRITICAL + 1)
else:
  logging.getLogger().setLevel(logging.DEBUG)

# Monkey patch to fix template loader issue:
#
# File "/usr/local/google_appengine/lib/django-1.4/django/template/loader.py", line 101, in find_template_loader:
# ImproperlyConfigured: Error importing template source loader django.template.loaders.filesystem.load_template_source: "'module' object has no attribute 'load_template_source'"
from django.template.loaders import filesystem
filesystem.load_template_source = filesystem._loader.load_template_source

# dumb hack to add the webutil dir to sys.path so the tests can be run from
# oauth-dropins even though they import webutil modules as top level
# (ie not from oauth_dropins.webutil import ...)
import os, sys
pkg = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
if pkg not in sys.path:
  sys.path.append(pkg)
