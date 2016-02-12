from mock import patch
import itertools

from django.test import TestCase


from core.db.backend.pg import PGBackend


class HelperMethods(TestCase):

    """Tests connections, validation and execution methods in PGBackend."""

    def setUp(self):
        # some words to test out
        self.good_nouns = ['good', 'good_noun', 'good-noun']

        # some words that shoudl throw validation errors
        self.bad_nouns = ['_foo', 'foo_', '-foo', 'foo-', 'foo bar',
                          'injection;attack', ';injection', 'injection;',
                          ]

        self.username = "username"
        self.password = "password"

        # mock open connection,
        # or else it will try to create a real db connection
        self.mock_psychopg = self.create_patch('core.db.backend.pg.psycopg2')

        # open mocked connection
        self.backend = PGBackend(self.username,
                                 self.password,
                                 repo_base=self.username)

    def create_patch(self, name):
        # helper method for creating patches
        patcher = patch(name)
        thing = patcher.start()
        self.addCleanup(patcher.stop)
        return thing

    def test_check_for_injections(self):
        """Tests validation against some sql injection attacks."""
        for noun in self.bad_nouns:
            with self.assertRaises(ValueError):
                self.backend._check_for_injections(noun)

        for noun in self.good_nouns:
            try:
                self.backend._check_for_injections(noun)
            except ValueError:
                self.fail('check_for_injections failed to verify a good name')

    def test_check_open_connections(self):
        self.assertTrue(self.mock_psychopg.connect.called)

    def test_execute_sql_strips_queries(self):
        query = ' This query needs stripping; '
        params = ('param1', 'param2')
        mock_cursor = self.mock_psychopg.connect.return_value.cursor
        mock_execute = mock_cursor.return_value.execute
        mock_cursor.return_value.fetchall.return_value = 'sometuples'
        mock_cursor.return_value.rowcount = 1000

        res = self.backend.execute_sql(query, params)

        self.assertTrue(mock_cursor.called)
        self.assertTrue(mock_execute.called)

        self.assertEqual(mock_execute.call_args[0][1], params)
        self.assertEqual(res['tuples'], 'sometuples')
        self.assertEqual(res['status'], True)
        self.assertEqual(res['row_count'], 1000)


class SchemaListCreateDeleteShare(TestCase):

    """
    Tests that items reach the execute_sql method in pg.py.

    Does not test execute_sql itself.
    """

    def setUp(self):
        # some words to test out
        self.good_nouns = ['good', 'good_noun', 'good-noun']
        # some words that shoudl throw validation errors
        self.bad_nouns = ['_foo', 'foo_', '-foo', 'foo-', 'foo bar',
                          'injection;attack', ';injection', 'injection;',
                          ]

        self.username = "username"
        self.password = "p4 sS_W&*^;0Rd$_"

        # mock the execute_sql function
        self.mock_execute_sql = self.create_patch(
            'core.db.backend.pg.PGBackend.execute_sql')
        self.mock_execute_sql.return_value = True

        # mock the is_valid_noun_name, which checks for injection attacks
        self.mock_check_for_injections = self.create_patch(
            'core.db.backend.pg.PGBackend._check_for_injections')

        # mock open connection, or else it will try to
        # create a real db connection
        self.mock_open_connection = self.create_patch(
            'core.db.backend.pg.PGBackend.__open_connection__')

        # mock the psycopg2.extensions.AsIs - many of the pg.py methods use it
        # Its return value (side effect) is the call value
        self.mock_as_is = self.create_patch('core.db.backend.pg.AsIs')
        self.mock_as_is.side_effect = lambda x: x

        # create an instance of PGBackend
        self.backend = PGBackend(self.username,
                                 self.password,
                                 repo_base=self.username)

    def create_patch(self, name):
        # helper method for creating patches
        patcher = patch(name)
        thing = patcher.start()
        self.addCleanup(patcher.stop)
        return thing

    def reset_mocks(self):
        # clears the mock call arguments and sets their call counts to 0
        self.mock_as_is.reset_mock()
        self.mock_execute_sql.reset_mock()
        self.mock_check_for_injections.reset_mock()

    # testing externally called methods in PGBackend
    def test_create_repo(self):
        create_repo_sql = 'CREATE SCHEMA IF NOT EXISTS %s AUTHORIZATION %s'
        reponame = 'reponame'
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [], 'fields': []}

        res = self.backend.create_repo(reponame)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], create_repo_sql)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1][0], reponame)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1][1], self.username)

        self.assertTrue(self.mock_as_is.called)
        self.assertTrue(self.mock_check_for_injections.called)
        self.assertEqual(res, True)

    def test_list_repos(self):
        # the user is already logged in, so there's not much to be tested here
        # except that the arguments are passed correctly
        list_repo_sql = ('SELECT schema_name AS repo_name '
                         'FROM information_schema.schemata '
                         'WHERE schema_owner != %s')

        mock_settings = self.create_patch("core.db.backend.pg.settings")
        mock_settings.DATABASES = {'default': {'USER': 'postgres'}}

        self.mock_execute_sql.return_value = {
            'status': True, 'row_count': 1, 'tuples': [
                ('test_table',)],
            'fields': [{'type': 1043, 'name': 'table_name'}]}

        params = (mock_settings.DATABASES['default']['USER'],)
        res = self.backend.list_repos()
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], list_repo_sql)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1], params)

        self.assertEqual(res, ['test_table'])

    def test_delete_repo_happy_path_cascade(self):
        drop_schema_sql = 'DROP SCHEMA %s %s'
        repo_name = 'repo_name'
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [], 'fields': []}

        res = self.backend.delete_repo(repo=repo_name, force=True)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], drop_schema_sql)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1][0], repo_name)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1][1], 'CASCADE')
        self.assertTrue(self.mock_as_is.called)
        self.assertTrue(self.mock_check_for_injections)
        self.assertEqual(res, True)

    def test_delete_repo_no_cascade(self):
        drop_schema_sql = 'DROP SCHEMA %s %s'
        repo_name = 'repo_name'
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [], 'fields': []}

        res = self.backend.delete_repo(repo=repo_name, force=False)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], drop_schema_sql)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1][0], repo_name)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1][1], None)
        self.assertTrue(self.mock_as_is.called)
        self.assertTrue(self.mock_check_for_injections.called)
        self.assertEqual(res, True)

    def test_add_collaborator(self):
        privileges = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                      'REFERENCES', 'TRIGGER', 'CREATE', 'CONNECT',
                      'TEMPORARY', 'EXECUTE', 'USAGE']

        add_collab_query = ('BEGIN;'
                            'GRANT USAGE ON SCHEMA %s TO %s;'
                            'GRANT %s ON ALL TABLES IN SCHEMA %s TO %s;'
                            'ALTER DEFAULT PRIVILEGES IN SCHEMA %s '
                            'GRANT %s ON TABLES TO %s;'
                            'COMMIT;'
                            )

        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [], 'fields': []}

        product = itertools.product(self.good_nouns, self.good_nouns,
                                    privileges)

        # test every combo here. For now, don't test combined privileges

        for repo, receiver, privilege in product:

            params = (repo, receiver, privilege, repo, receiver,
                      repo, privilege, receiver)

            res = self.backend.add_collaborator(
                repo=repo, collaborator=receiver, privileges=[privilege])

            self.assertEqual(
                self.mock_execute_sql.call_args[0][0], add_collab_query)
            self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
            self.assertEqual(self.mock_as_is.call_count, len(params))

            self.assertEqual(self.mock_check_for_injections.call_count, 3)
            self.assertEqual(res, True)

            self.reset_mocks()

    def test_add_collaborator_concatinates_privileges(self):
        privileges = ['SELECT', 'USAGE']
        repo = 'repo'
        receiver = 'receiver'
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [], 'fields': []}

        self.backend.add_collaborator(repo=repo,
                                      collaborator=receiver, privileges=privileges)

        # make sure that the privileges are passed as a string in params
        self.assertTrue(
            'SELECT, USAGE' in self.mock_execute_sql.call_args[0][1])

    def test_delete_collaborator(self):
        delete_collab_sql = ('BEGIN;'
                             'REVOKE ALL ON ALL TABLES IN SCHEMA %s '
                             'FROM %s CASCADE;'
                             'REVOKE ALL ON SCHEMA %s FROM %s CASCADE;'
                             'ALTER DEFAULT PRIVILEGES IN SCHEMA %s '
                             'REVOKE ALL ON TABLES FROM %s;'
                             'COMMIT;'
                             )
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [], 'fields': []}

        repo = 'repo_name'
        username = 'delete_me_user_name'

        params = (repo, username, repo, username, repo, username)
        res = self.backend.delete_collaborator(repo=repo, collaborator=username)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], delete_collab_sql)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, len(params))
        self.assertEqual(self.mock_check_for_injections.call_count, 2)
        self.assertEqual(res, True)

    def test_list_tables(self):
        repo = 'repo'
        list_tables_query = ('SELECT table_name FROM '
                             'information_schema.tables '
                             'WHERE table_schema = %s '
                             'AND table_type = \'BASE TABLE\';')
        params = (repo,)

        # execute sql should return this:
        self.mock_execute_sql.return_value = {
            'status': True, 'row_count': 1, 'tuples': [
                ('test_table',)],
            'fields': [{'type': 1043, 'name': 'table_name'}]}

        # mocking out execute_sql's complicated return JSON
        mock_list_repos = self.create_patch(
            'core.db.backend.pg.PGBackend.list_repos')
        mock_list_repos.return_value = [repo]

        res = self.backend.list_tables(repo)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], list_tables_query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_check_for_injections.call_count, 1)
        self.assertEqual(res, ['test_table'])

    def test_list_views(self):
        repo = 'repo'
        list_views_query = ('SELECT table_name FROM information_schema.tables '
                            'WHERE table_schema = %s '
                            'AND table_type = \'VIEW\';')
        params = (repo,)

        # mocking out execute_sql's complicated return JSON
        self.mock_execute_sql.return_value = {
            'status': True, 'row_count': 1, 'tuples': [
                ('test_view',)],
            'fields': [{'type': 1043, 'name': 'view_name'}]}

        # list_views depends on list_repos, which is being mocked out
        mock_list_repos = self.create_patch(
            'core.db.backend.pg.PGBackend.list_repos')
        mock_list_repos.return_value = [repo]

        res = self.backend.list_views(repo)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], list_views_query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_check_for_injections.call_count, 1)
        self.assertEqual(res, ['test_view'])

    def test_get_schema(self):

        self.mock_execute_sql.return_value = {
            'status': True, 'row_count': 2,
            'tuples': [(u'id', u'integer'), (u'words', u'text')],
            'fields': [
                {'type': 1043, 'name': 'column_name'},
                {'type': 1043, 'name': 'data_type'}
            ]
        }

        repo = 'repo'
        table = 'table'

        get_schema_query = ('SELECT column_name, data_type '
                            'FROM information_schema.columns '
                            'WHERE table_name = %s '
                            'AND table_schema = %s;'
                            )
        params = ('table', 'repo')

        self.backend.get_schema(repo, table)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], get_schema_query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_check_for_injections.call_count, 2)

    def test_create_user_no_create_db(self):
        create_user_query = ('CREATE ROLE %s WITH LOGIN '
                             'NOCREATEDB NOCREATEROLE NOCREATEUSER '
                             'PASSWORD %s')

        username = 'username'
        password = 'password'

        self.backend.create_user(username, password, create_db=False)
        params = (username, password)
        mock_create_user_database = self.create_patch(
            'core.db.backend.pg.PGBackend.create_user_database')

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], create_user_query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 1)
        self.assertEqual(self.mock_check_for_injections.call_count, 1)
        self.assertFalse(mock_create_user_database.called)

    def test_create_user_calls_create_db(self):
        username = 'username'
        password = 'password'
        mock_create_user_database = self.create_patch(
            'core.db.backend.pg.PGBackend.create_user_database')

        self.backend.create_user(
            username=username, password=password, create_db=True)
        self.assertTrue(mock_create_user_database.called)

    def test_create_user_db(self):
        create_db_query_1 = 'CREATE DATABASE %s; '
        create_db_query_2 = 'ALTER DATABASE %s OWNER TO %s; '
        username = 'username'

        self.backend.create_user_database(username)
        params_1 = (username,)
        params_2 = (username, username)

        call_args_1 = self.mock_execute_sql.call_args_list[0][0]
        self.assertEqual(call_args_1[0], create_db_query_1)
        self.assertEqual(call_args_1[1], params_1)

        call_args_2 = self.mock_execute_sql.call_args_list[1][0]
        self.assertEqual(call_args_2[0], create_db_query_2)
        self.assertEqual(call_args_2[1], params_2)

        self.assertEqual(self.mock_as_is.call_count, len(params_1 + params_2))
        self.assertEqual(self.mock_check_for_injections.call_count, 1)

    def test_remove_user(self):
        query = 'DROP ROLE %s;'
        username = "username"
        params = (username,)
        self.backend.remove_user(username)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, len(params))
        self.assertEqual(self.mock_check_for_injections.call_count, 1)

    def test_remove_database(self):
        # mock out list_all_users
        mock_list_all_users = self.create_patch(
            'core.db.backend.pg.PGBackend.list_all_users')
        mock_list_all_users.return_value = ['tweedledee', 'tweedledum']

        self.backend.remove_database(self.username)

        # revoke statement stuff
        revoke_query = 'REVOKE ALL ON DATABASE %s FROM %s;'
        revoke_params_1 = (self.username, 'tweedledee')
        revoke_params_2 = (self.username, 'tweedledum')

        self.assertEqual(
            self.mock_execute_sql.call_args_list[0][0][0], revoke_query)
        self.assertEqual(
            self.mock_execute_sql.call_args_list[0][0][1], revoke_params_1)

        self.assertEqual(
            self.mock_execute_sql.call_args_list[1][0][0], revoke_query)
        self.assertEqual(
            self.mock_execute_sql.call_args_list[1][0][1], revoke_params_2)

        # drop statement stuff
        drop_query = 'DROP DATABASE %s;'
        drop_params = (self.username,)

        self.assertEqual(
            self.mock_execute_sql.call_args_list[2][0][0], drop_query)
        self.assertEqual(
            self.mock_execute_sql.call_args_list[2][0][1], drop_params)
        self.assertEqual(self.mock_as_is.call_count, 5)
        self.assertEqual(self.mock_check_for_injections.call_count, 1)

    def test_change_password(self):
        query = 'ALTER ROLE %s WITH PASSWORD %s;'
        params = (self.username, self.password)
        self.backend.change_password(self.username, self.password)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 1)
        self.assertEqual(self.mock_check_for_injections.call_count, 1)

    def test_list_collaborators(self):
        query = 'SELECT unnest(nspacl) FROM pg_namespace WHERE nspname=%s;'
        repo = 'repo_name'
        params = (repo, )

        self.mock_execute_sql.return_value = {
            'status': True, 'row_count': 2,
            'tuples': [
                ('al_carter=UC/al_carter',),
                ('foo_bar=U/al_carter',)
            ],
            'fields': [{'type': 1033, 'name': 'unnest'}]}

        expected_result = [
            {'username': 'al_carter', 'permissions': 'UC'},
            {'username': 'foo_bar', 'permissions': 'U'}
            ]

        res = self.backend.list_collaborators(repo)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1], params)
        self.assertFalse(self.mock_as_is.called)
        self.assertEqual(res, expected_result)

    def test_list_all_users(self):
        query = 'SELECT usename FROM pg_catalog.pg_user WHERE usename != %s'
        params = (self.username,)
        self.mock_execute_sql.return_value = {
            'status': True, 'row_count': 2,
            'tuples': [(u'delete_me_alpha_user',), (u'delete_me_beta_user',)],
            'fields': [{'type': 19, 'name': 'usename'}]
            }

        res = self.backend.list_all_users()

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(
            self.mock_execute_sql.call_args[0][1], params)
        self.assertFalse(self.mock_as_is.called)
        self.assertEqual(res, ['delete_me_alpha_user', 'delete_me_beta_user'])

    def test_has_base_privilege(self):
        query = 'SELECT has_database_privilege(%s, %s);'
        privilege = 'CONNECT'
        params = (self.username, privilege)
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [[True]], 'fields': []}

        res = self.backend.has_base_privilege(
            login=self.username, privilege=privilege)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 0)
        self.assertEqual(res, True)

    def test_has_repo_privilege(self):
        query = 'SELECT has_schema_privilege(%s, %s, %s);'
        repo = 'repo'
        privilege = 'CONNECT'
        params = (self.username, repo, privilege)
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [[True]], 'fields': []}

        res = self.backend.has_repo_privilege(
            login=self.username, repo=repo, privilege=privilege)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 0)
        self.assertEqual(res, True)

    def test_has_table_privilege(self):
        query = 'SELECT has_table_privilege(%s, %s, %s);'
        table = 'table'
        privilege = 'CONNECT'
        params = (self.username, table, privilege)
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [[True]], 'fields': []}
        res = self.backend.has_table_privilege(
            login=self.username, table=table, privilege=privilege)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 0)
        self.assertEqual(res, True)

    def test_has_column_privilege(self):
        query = 'SELECT has_column_privilege(%s, %s, %s, %s);'
        table = 'table'
        column = 'column'
        privilege = 'CONNECT'
        params = (self.username, table, column, privilege)
        self.mock_execute_sql.return_value = {'status': True, 'row_count': -1,
                                              'tuples': [[True]], 'fields': []}

        res = self.backend.has_column_privilege(
            login=self.username, table=table,
            column=column, privilege=privilege)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 0)
        self.assertEqual(res, True)

    def test_export_table_with_header(self):
        query = 'COPY %s TO %s WITH %s %s DELIMITER %s;'
        table_name = 'user_name.repo_name.table_name'
        file_path = 'file_path'
        file_format = 'file_format'
        delimiter = ','
        header = True

        params = (table_name, file_path, file_format, 'HEADER', delimiter)
        self.backend.export_table(table_name, file_path,
                                  file_format, delimiter, header)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 3)
        self.assertEqual(self.mock_check_for_injections.call_count, 4)

    def test_export_table_with_no_header(self):
        table_name = 'table_name'
        file_path = 'file_path'
        file_format = 'file_format'
        delimiter = ','
        header = False

        params = (table_name, file_path, file_format, '', delimiter)
        self.backend.export_table(table_name, file_path,
                                  file_format, delimiter, header)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][1], params)

    def test_export_query_with_header(self):
        query = 'COPY (%s) TO %s WITH %s %s DELIMITER %s;'

        passed_query = 'myquery'
        file_path = 'file_path'
        file_format = 'CSV'
        delimiter = ','
        header = True

        params = (passed_query, file_path, file_format, 'HEADER', delimiter)
        self.backend.export_query(passed_query, file_path,
                                  file_format, delimiter, header)

        self.assertEqual(
            self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 3)
        self.assertEqual(self.mock_check_for_injections.call_count, 2)

    def test_export_query_with_no_header(self):
        passed_query = 'myquery'
        file_path = 'file_path'
        file_format = 'CSV'
        delimiter = ','
        header = False

        params = (passed_query, file_path, file_format, '', delimiter)
        self.backend.export_query(passed_query, file_path,
                                  file_format, delimiter, header)

        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)

    def test_export_query_only_executes_text_before_semicolon(self):
        passed_query = ' text before semicolon; text after; '
        file_path = 'file_path'
        file_format = 'CSV'
        delimiter = ','
        header = False

        passed_query_cleaned = ' text before semicolon'
        params = (passed_query_cleaned, file_path, file_format, '', delimiter)
        self.backend.export_query(passed_query, file_path,
                                  file_format, delimiter, header)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)

    def test_import_file_with_header(self):
        query = 'COPY %s FROM %s WITH %s %s DELIMITER %s ENCODING %s QUOTE %s;'
        table_name = 'user_name.repo_name.table_name'
        file_path = 'file_path'
        file_format = 'file_format'
        delimiter = ','
        header = True
        encoding = 'ISO-8859-1'
        quote_character = '"'

        params = (table_name, file_path, file_format,
                  'HEADER', delimiter, encoding, quote_character)
        self.backend.import_file(table_name, file_path, file_format, delimiter,
                                 header, encoding, quote_character)

        self.assertEqual(self.mock_execute_sql.call_args[0][0], query)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)
        self.assertEqual(self.mock_as_is.call_count, 3)
        self.assertEqual(self.mock_check_for_injections. call_count, 5)

    def test_import_table_with_no_header(self):
        table_name = 'table_name'
        file_path = 'file_path'
        file_format = 'file_format'
        delimiter = ','
        header = False
        encoding = 'ISO-8859-1'
        quote_character = '"'

        params = (table_name, file_path, file_format,
                  '', delimiter, encoding, quote_character)
        self.backend.import_file(table_name, file_path, file_format, delimiter,
                                 header, encoding, quote_character)
        self.assertEqual(self.mock_execute_sql.call_args[0][1], params)

    def test_import_file_w_dbtruck(self):
        # DBTruck is not tested for safety/security... At all.
        # The method does so little
        # that it doesn't even make much sense to test it.
        pass
