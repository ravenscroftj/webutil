#!/usr/bin/python
"""Misc utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
import functools
import logging
import re
import urlparse
import webapp2
from webob import exc

from google.appengine.api import urlfetch as gae_urlfetch
from google.appengine.ext import db


class Struct(object):
  """A generic class that initializes its attributes from constructor kwargs."""
  def __init__(self, **kwargs):
    vars(self).update(**kwargs)


def to_xml(value):
  """Renders a dict (usually from JSON) as an XML snippet."""
  if isinstance(value, dict):
    if not value:
      return ''
    elems = []
    for key, vals in value.iteritems():
      if not isinstance(vals, (list, tuple)):
        vals = [vals]
      elems.extend(u'<%s>%s</%s>' % (key, to_xml(val), key) for val in vals)
    return '\n' + '\n'.join(elems) + '\n'
  else:
    if value is None:
      value = ''
    return unicode(value)


def trim_nulls(value):
  """Recursively removes dict elements with None or empty values."""
  if isinstance(value, dict):
    return dict((k, trim_nulls(v)) for k, v in value.items()
                if trim_nulls(v) not in (None, {}, [], ()))
  elif isinstance(value, list):
    return [trim_nulls(v) for v in value]
  else:
    return value


def urlfetch(url, **kwargs):
  """Wraps urlfetch. Passes error responses through to the client.

  ...by raising HTTPException.

  Args:
    url: str
    kwargs: passed through to urlfetch.fetch()

  Returns:
    the HTTP response body
  """
  logging.debug('Fetching %s with kwargs %s', url, kwargs)
  resp = gae_urlfetch.fetch(url, deadline=999, **kwargs)

  if resp.status_code == 200:
    return resp.content
  else:
    logging.debug('GET %s returned %d', url, resp.status_code)
    webapp2.abort(resp.status_code, body_template=resp.content,
                  headers=resp.headers)


def tag_uri(domain, name):
  """Returns a tag URI string for the given domain and name.

  Example return value: 'tag:twitter.com,2012:snarfed_org/172417043893731329'

  Background on tag URIs: http://taguri.org/
  """
  return 'tag:%s,%d:%s' % (domain, datetime.datetime.now().year, name)


def parse_acct_uri(uri, hosts=None):
  """Parses acct: URIs of the form acct:user@example.com .

  Background: http://hueniverse.com/2009/08/making-the-case-for-a-new-acct-uri-scheme/

  Args:
    uri: string
    hosts: sequence of allowed hosts (usually domains). None means allow all.

  Returns: (username, host) tuple

  Raises: ValueError if the uri is invalid or the host isn't allowed.
  """
  parsed = urlparse.urlparse(uri)
  if parsed.scheme and parsed.scheme != 'acct':
    raise ValueError('Acct URI %s has unsupported scheme: %s' %
                     (uri, parsed.scheme))

  try:
    username, host = parsed.path.split('@')
    assert username, host
  except ValueError, AssertionError:
    raise ValueError('Bad acct URI: %s' % uri)

  if hosts is not None and host not in hosts:
    raise ValueError('Acct URI %s has unsupported host %s; expected %r.' %
                     (uri, host, hosts))

  return username, host


def favicon_for_url(url):
  return 'http://%s/favicon.ico' % urlparse.urlparse(url).netloc

def domain_from_link(url):
    parsed = urlparse.urlparse(url)
    if not parsed.netloc:
      parsed = urlparse.urlparse('http://' + url)

    domain = parsed.netloc
    if not domain:
      raise exc.HTTPBadRequest('No domain found in %r' % url)

    # strip exactly one dot from the right, if present
    if domain[-1:] == ".":
      domain = domain[:-1]

    # http://stackoverflow.com/questions/2532053/validate-hostname-string-in-python
    allowed = re.compile('(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    split = domain.split('.')
    for part in split:
      if not allowed.match(part):
        raise exc.HTTPBadRequest('Bad component in domain: %r' % part)

    return domain


def linkify(text):
  """Adds HTML links to URLs in the given plain text.

  For example: linkify("Hello http://tornadoweb.org!") would return
  Hello <a href="http://tornadoweb.org">http://tornadoweb.org</a>!

  Ignores URLs that are inside HTML links, ie anchor tags that look like
  <a href="..."> .

  Based on https://github.com/silas/huck/blob/master/huck/utils.py#L59
  """
  # I originally used the regex from
  # http://daringfireball.net/2010/07/improved_regex_for_matching_urls
  # but it gets all exponential on certain patterns (such as too many trailing
  # dots), causing the regex matcher to never return. This regex should avoid
  # those problems.
  _URL_RE = re.compile(ur"""
(?<! href=["'])  # negative lookahead for beginning of HTML anchor tag
\b((?:([\w-]+):(/{1,3})|www[.])(?:(?:(?:[^\s&()]|&amp;|&quo
t;)*(?:[^!"#$%&'()*+,.:;<=>?@\[\]^`{|}~\s]))|(?:\((?:[^\s&()]|&amp;|&quot;)*\)))+)
(?![^<>]*>)  # negative lookahead for end of HTML anchor tag
""", re.VERBOSE)

  def make_link(m):
    url = m.group(1)
    proto = m.group(2)
    href = m.group(1)
    if not proto:
      href = 'http://' + href
    return u'<a href="%s">%s</a>' % (href, url)

  return _URL_RE.sub(make_link, text)


class SimpleTzinfo(datetime.tzinfo):
  """A simple, DST-unaware tzinfo subclass.
  """

  offset = datetime.timedelta(0)

  def utcoffset(self, dt):
    return self.offset

  def dst(self, dt):
    return datetime.timedelta(0)


def parse_iso8601(str):
  """Parses an ISO 8601 date/time string and returns a datetime object.

  Time zone designator is optional. If present, the returned datetime will be
  time zone aware.

  Args:
    str: string ISO 8601, e.g. '2012-07-23T05:54:49+0000'

  Returns: datetime
  """
  # grr, this would be way easier if strptime supported %z, but evidently that
  # was only added in python 3.2.
  # http://stackoverflow.com/questions/9959778/is-there-a-wildcard-format-directive-for-strptime
  try:
    base, zone = re.match('(.{19})([+-][0-9]{4})?', str).groups()
  except AttributeError, e:
    raise ValueError(e)

  tz = None
  if zone:
    tz = SimpleTzinfo()
    tz.offset = (datetime.datetime.strptime(zone[1:], '%H%M') -
                 datetime.datetime.strptime('', ''))
    if zone[0] == '-':
      tz.offset = -tz.offset

  return datetime.datetime.strptime(base, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)


def maybe_iso8601_to_rfc3339(input):
  """Tries to convert an ISO 8601 date/time string to RFC 3339.

  The formats are similar, but not identical, eg. RFC 3339 includes a colon in
  the timezone offset at the end (+0000 instead of +00:00), but ISO 8601
  doesn't.

  If the input can't be parsed as ISO 8601, it's silently returned, unchanged!

  http://www.rfc-editor.org/rfc/rfc3339.txt
  """
  try:
    return parse_iso8601(input).isoformat('T')
  except (ValueError, TypeError):
    return input


def maybe_timestamp_to_rfc3339(input):
  """Tries to convert a string or int UNIX timestamp to RFC 3339."""
  try:
    return datetime.datetime.fromtimestamp(int(input)).isoformat('T')
  except (ValueError, TypeError):
    return input


class KeyNameModel(db.Model):
  """A model class that requires a key name."""

  def __init__(self, *args, **kwargs):
    """Raises AssertionError if key name is not provided."""
    super(KeyNameModel, self).__init__(*args, **kwargs)
    try:
      assert self.key().name()
    except db.NotSavedError:
      assert False, 'key name required but not provided'


class SingleEGModel(db.Model):
  """A model class that stores all entities in a single entity group.

  All entities use the same parent key (below), and all() automatically adds it
  as an ancestor. That allows, among other things, fetching all entities of
  this kind with strong consistency.
  """

  def enforce_parent(fn):
    """Sets the parent keyword arg. If it's already set, checks that it's correct."""
    @functools.wraps(fn)
    def wrapper(self_or_cls, *args, **kwargs):
      if '_from_entity' not in kwargs:
        parent = self_or_cls.shared_parent_key()
        if 'parent' in kwargs:
          assert kwargs['parent'] == parent, "Can't override parent in SingleEGModel"
        kwargs['parent'] = parent

      return fn(self_or_cls, *args, **kwargs)

    return wrapper

  @classmethod
  def shared_parent_key(cls):
    """Returns the shared parent key for this class.

    It's not actually an entity, just a placeholder key.
    """
    return db.Key.from_path('Parent', cls.kind())

  @enforce_parent
  def __init__(self, *args, **kwargs):
    super(SingleEGModel, self).__init__(*args, **kwargs)

  @classmethod
  @enforce_parent
  def get_by_id(cls, id, **kwargs):
    return super(SingleEGModel, cls).get_by_id(id, **kwargs)

  @classmethod
  @enforce_parent
  def get_by_key_name(cls, key_name, **kwargs):
    return super(SingleEGModel, cls).get_by_key_name(key_name, **kwargs)

  @classmethod
  @enforce_parent
  def get_or_insert(cls, key_name, **kwargs):
    return super(SingleEGModel, cls).get_or_insert(key_name, **kwargs)

  @classmethod
  def all(cls):
    return db.Query(cls).ancestor(cls.shared_parent_key())
