from sqlalchemy.testing import assert_raises, assert_raises_message, eq_
import ConfigParser
import StringIO
import sqlalchemy.engine.url as url
from sqlalchemy import create_engine, engine_from_config, exc, pool
from sqlalchemy.engine.util import _coerce_config
from sqlalchemy.engine.default import DefaultDialect
import sqlalchemy as tsa
from sqlalchemy.testing import fixtures
from sqlalchemy import testing
from sqlalchemy.testing.mock import Mock


class ParseConnectTest(fixtures.TestBase):
    def test_rfc1738(self):
        for text in (
            'dbtype://username:password@hostspec:110//usr/db_file.db',
            'dbtype://username:password@hostspec/database',
            'dbtype://username:password@hostspec',
            'dbtype://username:password@/database',
            'dbtype://username@hostspec',
            'dbtype://username:password@127.0.0.1:1521',
            'dbtype://hostspec/database',
            'dbtype://hostspec',
            'dbtype://hostspec/?arg1=val1&arg2=val2',
            'dbtype:///database',
            'dbtype:///:memory:',
            'dbtype:///foo/bar/im/a/file',
            'dbtype:///E:/work/src/LEM/db/hello.db',
            'dbtype:///E:/work/src/LEM/db/hello.db?foo=bar&hoho=lala',
            'dbtype://',
            'dbtype://username:password@/db',
            'dbtype:////usr/local/mailman/lists/_xtest@example.com/memb'
                'ers.db',
            'dbtype://username:apples%2Foranges@hostspec/mydatabase',
            ):
            u = url.make_url(text)
            assert u.drivername == 'dbtype'
            assert u.username == 'username' or u.username is None
            assert u.password == 'password' or u.password \
                == 'apples/oranges' or u.password is None
            assert u.host == 'hostspec' or u.host == '127.0.0.1' \
                or not u.host
            assert str(u) == text

class DialectImportTest(fixtures.TestBase):
    def test_import_base_dialects(self):

        # the globals() somehow makes it for the exec() + nose3.

        for name in (
            'mysql',
            'firebird',
            'postgresql',
            'sqlite',
            'oracle',
            'mssql',
            ):
            exec ('from sqlalchemy.dialects import %s\ndialect = '
                  '%s.dialect()' % (name, name), globals())
            eq_(dialect.name, name)

class CreateEngineTest(fixtures.TestBase):
    """test that create_engine arguments of different types get
    propagated properly"""

    def test_connect_query(self):
        dbapi = MockDBAPI(foober='12', lala='18', fooz='somevalue')
        e = \
            create_engine('postgresql://scott:tiger@somehost/test?foobe'
                          'r=12&lala=18&fooz=somevalue', module=dbapi,
                          _initialize=False)
        c = e.connect()

    def test_kwargs(self):
        dbapi = MockDBAPI(foober=12, lala=18, hoho={'this': 'dict'},
                          fooz='somevalue')
        e = \
            create_engine('postgresql://scott:tiger@somehost/test?fooz='
                          'somevalue', connect_args={'foober': 12,
                          'lala': 18, 'hoho': {'this': 'dict'}},
                          module=dbapi, _initialize=False)
        c = e.connect()

    def test_coerce_config(self):
        raw = r"""
[prefixed]
sqlalchemy.url=postgresql://scott:tiger@somehost/test?fooz=somevalue
sqlalchemy.convert_unicode=0
sqlalchemy.echo=false
sqlalchemy.echo_pool=1
sqlalchemy.max_overflow=2
sqlalchemy.pool_recycle=50
sqlalchemy.pool_size=2
sqlalchemy.pool_threadlocal=1
sqlalchemy.pool_timeout=10
[plain]
url=postgresql://scott:tiger@somehost/test?fooz=somevalue
convert_unicode=0
echo=0
echo_pool=1
max_overflow=2
pool_recycle=50
pool_size=2
pool_threadlocal=1
pool_timeout=10
"""
        ini = ConfigParser.ConfigParser()
        ini.readfp(StringIO.StringIO(raw))

        expected = {
            'url': 'postgresql://scott:tiger@somehost/test?fooz=somevalue',
            'convert_unicode': 0,
            'echo': False,
            'echo_pool': True,
            'max_overflow': 2,
            'pool_recycle': 50,
            'pool_size': 2,
            'pool_threadlocal': True,
            'pool_timeout': 10,
            }

        prefixed = dict(ini.items('prefixed'))
        self.assert_(_coerce_config(prefixed, 'sqlalchemy.')
                     == expected)

        plain = dict(ini.items('plain'))
        self.assert_(_coerce_config(plain, '') == expected)

    def test_engine_from_config(self):
        dbapi = mock_dbapi

        config = \
            {'sqlalchemy.url': 'postgresql://scott:tiger@somehost/test'\
             '?fooz=somevalue', 'sqlalchemy.pool_recycle': '50',
             'sqlalchemy.echo': 'true'}

        e = engine_from_config(config, module=dbapi, _initialize=False)
        assert e.pool._recycle == 50
        assert e.url \
            == url.make_url('postgresql://scott:tiger@somehost/test?foo'
                            'z=somevalue')
        assert e.echo is True

        for param, values in [
            ('convert_unicode', ('true', 'false', 'force')),
            ('echo', ('true', 'false', 'debug')),
            ('echo_pool', ('true', 'false', 'debug')),
            ('use_native_unicode', ('true', 'false')),
        ]:
            for value in values:
                config = {
                        'sqlalchemy.url': 'postgresql://scott:tiger@somehost/test',
                        'sqlalchemy.%s' % param : value
                }
                cfg = _coerce_config(config, 'sqlalchemy.')
                assert cfg[param] == {'true':True, 'false':False}.get(value, value)


    def test_custom(self):
        dbapi = MockDBAPI(foober=12, lala=18, hoho={'this': 'dict'},
                          fooz='somevalue')

        def connect():
            return dbapi.connect(foober=12, lala=18, fooz='somevalue',
                                 hoho={'this': 'dict'})

        # start the postgresql dialect, but put our mock DBAPI as the
        # module instead of psycopg

        e = create_engine('postgresql://', creator=connect,
                          module=dbapi, _initialize=False)
        c = e.connect()

    def test_recycle(self):
        dbapi = MockDBAPI(foober=12, lala=18, hoho={'this': 'dict'},
                          fooz='somevalue')
        e = create_engine('postgresql://', pool_recycle=472,
                          module=dbapi, _initialize=False)
        assert e.pool._recycle == 472

    def test_reset_on_return(self):
        dbapi = MockDBAPI(foober=12, lala=18, hoho={'this': 'dict'},
                          fooz='somevalue')
        for (value, expected) in [
            ('rollback', pool.reset_rollback),
            ('commit', pool.reset_commit),
            (None, pool.reset_none),
            (True, pool.reset_rollback),
            (False, pool.reset_none),
        ]:
            e = create_engine('postgresql://', pool_reset_on_return=value,
                          module=dbapi, _initialize=False)
            assert e.pool._reset_on_return is expected

        assert_raises(
            exc.ArgumentError,
            create_engine, "postgresql://",
            pool_reset_on_return='hi', module=dbapi,
            _initialize=False
        )

    def test_bad_args(self):
        assert_raises(exc.ArgumentError, create_engine, 'foobar://',
                      module=mock_dbapi)

        # bad arg

        assert_raises(TypeError, create_engine, 'postgresql://',
                      use_ansi=True, module=mock_dbapi)

        # bad arg

        assert_raises(
            TypeError,
            create_engine,
            'oracle://',
            lala=5,
            use_ansi=True,
            module=mock_dbapi,
            )
        assert_raises(TypeError, create_engine, 'postgresql://',
                      lala=5, module=mock_dbapi)
        assert_raises(TypeError, create_engine, 'sqlite://', lala=5,
                      module=mock_sqlite_dbapi)
        assert_raises(TypeError, create_engine, 'mysql+mysqldb://',
                      use_unicode=True, module=mock_dbapi)

    @testing.requires.sqlite
    def test_wraps_connect_in_dbapi(self):
        # sqlite uses SingletonThreadPool which doesnt have max_overflow

        assert_raises(TypeError, create_engine, 'sqlite://',
                      max_overflow=5, module=mock_sqlite_dbapi)
        e = create_engine('sqlite://', connect_args={'use_unicode'
                          : True}, convert_unicode=True)
        try:
            e.connect()
        except tsa.exc.DBAPIError, de:
            assert not de.connection_invalidated

    def test_ensure_dialect_does_is_disconnect_no_conn(self):
        """test that is_disconnect() doesn't choke if no connection, cursor given."""
        dialect = testing.db.dialect
        dbapi = dialect.dbapi
        assert not dialect.is_disconnect(dbapi.OperationalError("test"), None, None)

    @testing.requires.sqlite
    def test_invalidate_on_connect(self):
        """test that is_disconnect() is called during connect.

        interpretation of connection failures are not supported by
        every backend.

        """

        e = create_engine('sqlite://')
        sqlite3 = e.dialect.dbapi

        dbapi = MockDBAPI()
        dbapi.Error = sqlite3.Error,
        dbapi.ProgrammingError = sqlite3.ProgrammingError
        dbapi.connect = Mock(side_effect=sqlite3.ProgrammingError(
                                    "Cannot operate on a closed database."))
        try:
            create_engine('sqlite://', module=dbapi).connect()
            assert False
        except tsa.exc.DBAPIError, de:
            assert de.connection_invalidated

    def test_urlattr(self):
        """test the url attribute on ``Engine``."""

        e = create_engine('mysql://scott:tiger@localhost/test',
                          module=mock_dbapi, _initialize=False)
        u = url.make_url('mysql://scott:tiger@localhost/test')
        e2 = create_engine(u, module=mock_dbapi, _initialize=False)
        assert e.url.drivername == e2.url.drivername == 'mysql'
        assert e.url.username == e2.url.username == 'scott'
        assert e2.url is u

    def test_poolargs(self):
        """test that connection pool args make it thru"""

        e = create_engine(
            'postgresql://',
            creator=None,
            pool_recycle=50,
            echo_pool=None,
            module=mock_dbapi,
            _initialize=False,
            )
        assert e.pool._recycle == 50

        # these args work for QueuePool

        e = create_engine(
            'postgresql://',
            max_overflow=8,
            pool_timeout=60,
            poolclass=tsa.pool.QueuePool,
            module=mock_dbapi,
            _initialize=False,
            )

        # but not SingletonThreadPool

        assert_raises(
            TypeError,
            create_engine,
            'sqlite://',
            max_overflow=8,
            pool_timeout=60,
            poolclass=tsa.pool.SingletonThreadPool,
            module=mock_sqlite_dbapi,
            _initialize=False,
            )

class TestRegNewDBAPI(fixtures.TestBase):
    def test_register_base(self):
        from sqlalchemy.dialects import registry
        registry.register("mockdialect", __name__, "MockDialect")

        e = create_engine("mockdialect://")
        assert isinstance(e.dialect, MockDialect)

    def test_register_dotted(self):
        from sqlalchemy.dialects import registry
        registry.register("mockdialect.foob", __name__, "MockDialect")

        e = create_engine("mockdialect+foob://")
        assert isinstance(e.dialect, MockDialect)

    def test_register_legacy(self):
        from sqlalchemy.dialects import registry
        tokens = __name__.split(".")

        global dialect
        dialect = MockDialect
        registry.register("mockdialect.foob", ".".join(tokens[0:-1]), tokens[-1])

        e = create_engine("mockdialect+foob://")
        assert isinstance(e.dialect, MockDialect)

    def test_register_per_dbapi(self):
        from sqlalchemy.dialects import registry
        registry.register("mysql.my_mock_dialect", __name__, "MockDialect")

        e = create_engine("mysql+my_mock_dialect://")
        assert isinstance(e.dialect, MockDialect)

class MockDialect(DefaultDialect):
    @classmethod
    def dbapi(cls, **kw):
        return MockDBAPI()

def MockDBAPI(**assert_kwargs):
    connection = Mock(get_server_version_info=Mock(return_value='5.0'))
    def connect(*args, **kwargs):
        for k in assert_kwargs:
            assert k in kwargs, 'key %s not present in dictionary' % k
            eq_(
                kwargs[k], assert_kwargs[k]
            )
        return connection

    return Mock(
                sqlite_version_info=(99, 9, 9,),
                version_info=(99, 9, 9,),
                sqlite_version='99.9.9',
                paramstyle='named',
                connect=Mock(side_effect=connect)
            )

mock_dbapi = MockDBAPI()
mock_sqlite_dbapi = msd = MockDBAPI()
