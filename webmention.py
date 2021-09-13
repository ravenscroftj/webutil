"""Webmention endpoint discovery and sending.

Spec: https://webmention.net/draft/
"""
from collections import namedtuple
import logging
import re
from urllib.parse import urlparse, urljoin

from . import util

LINK_HEADER_RE = re.compile(
  r'''<([^>]+)>; rel=["']?(https?://)?webmention(\.org/?)?["']?''')

# Returned by discover(). Attributes:
#   endpoint: str
#   response: requests.Response
Endpoint = namedtuple('Endpoint', ('endpoint', 'response'))


def discover(url, **requests_kwargs):
  """Discovers a URL's webmention endpoint.

  Args:
    url: str
    requests_kwargs: passed to :meth:`requests.post`

  Returns: :class:`Endpoint`. If no endpoint is discovered, the endpoint
  attribute will be None.

  Raises: :class:`ValueError` on bad URL, :class:`requests.HTTPError` on failure
  """
  if not url or not isinstance(url, str) or not urlparse(url).netloc:
      raise ValueError(url)

  logging.debug(f'Webmention discovery: attempting for {url}')

  resp = util.requests_get(url, **requests_kwargs)
  # We ignore HTTP status code and allow discovery to continue even on non-2xx
  # responses because the spec doesn't say to stop on error status codes.
  # Background:
  # https://www.w3.org/TR/webmention/#sender-discovers-receiver-webmention-endpoint
  # https://github.com/snarfed/bridgy/issues/1012

  # look in headers
  for link in resp.headers.get('Link', '').split(','):
    match = LINK_HEADER_RE.search(link)
    if match:
      endpoint = util.fragmentless(urljoin(url, match.group(1)))
      logging.debug(f'Webmention discovery: got endpoint in Link header: {endpoint}')
      return Endpoint(endpoint, resp)

  # if no header, require HTML content
  content_type = resp.headers.get('content-type')
  if content_type and content_type.split(';')[0] != 'text/html':
    logging.debug(f'Webmention discovery: no endpoint in headers and content type {content_type} is not HTML')
    return Endpoint(None, resp)

  # look in the content
  soup = util.parse_html(resp.text)
  for tag in soup.find_all(
      ('link', 'a'), attrs={'rel': ('webmention', 'http://webmention.org/')}):
    if tag and tag.get('href'):
      endpoint = util.fragmentless(urljoin(url, tag['href']))
      logging.debug(f'Webmention discovery: got endpoint in tag: {endpoint}')
      return Endpoint(endpoint, resp)

  logging.debug('Webmention discovery: no endpoint in headers or HTML')
  return Endpoint(None, resp)


def send(endpoint, source, target, **requests_kwargs):
  """Sends a webmention.

  Args:
    endpoint: str, webmention endpoint URL
    source: str, source URL
    target: str, target URL
    requests_kwargs: passed to :meth:`requests.post`

  Returns: :class:`requests.Response` on success.

  Raises: :class:`ValueError` on bad URL, :class:`requests.HTTPError` on failure
  """
  for arg in endpoint, source, target:
    if not arg or not isinstance(arg, str) or not urlparse(arg).netloc:
      raise ValueError(arg)

  logging.debug(f'webmention send: {source} -> {target}')

  requests_kwargs.setdefault('headers', {})['Accept'] = '*/*'
  try:
    # following 3xx redirects translates POST to GET, which we don't want,
    # so disable that. https://github.com/snarfed/bridgy/issues/753
    resp = util.requests_post(endpoint, data={'source': source, 'target': target},
                              allow_redirects=False, **requests_kwargs)
  except BaseException as e:
    logging.debug(f'webmention send: got {e.__class__.__name__}')
    raise

  logging.debug(f'webmention send: got HTTP {resp.status_code}')
  resp.raise_for_status()
  return resp
