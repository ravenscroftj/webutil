"""Unit tests for models.py.
"""
import warnings

from google.cloud import ndb

from ..models import StringIdModel
from .. import testutil


class StringIdModelTest(testutil.TestCase):

  def setUp(self):
    warnings.filterwarnings('ignore', module='google.auth',
      message='Your application has authenticated using end user credentials')

  def test_put(self):
    with ndb.Client().context():
      self.assertEqual(ndb.Key(StringIdModel, 'x'),
                       StringIdModel(id='x').put())
      self.assertRaises(AssertionError, StringIdModel().put)
      self.assertRaises(AssertionError, StringIdModel(id=1).put)
