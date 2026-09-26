"""Native A07 PostgreSQL schema admission for an owned disposable target.

Prepared for CI. PostgreSQL runtime has NOT been executed in the authoring
environment. SQLite SQL is never translated into a guessed PostgreSQL oracle:
the same ProjectState is rendered in a new owned reference schema on the same
server and compared through pg_catalog. No source migrations are executed.
"""
from copy import deepcopy
import json
import re
from uuid import uuid4


def q(value):
    return '"' + str(value).replace('"', '""') + '"'


def _fetch(connection, sql, parameters=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


def _one(connection, sql, parameters=()):
    rows = _fetch(connection, sql, parameters)
    if len(rows) != 1:
        raise ValueError('Expected exactly one catalog identity row')
    return rows[0]


def _expression(value, schema):
    """Normalize only the local schema qualifier in native deparsed SQL.

    Preserve strings, quoted identifiers, casts, operators, parentheses and
    order. pg_get_expr/pg_get_constraintdef on the same server is the oracle.
    This lexer does not infer algebraic equivalence or rewrite constraints.
    """
    if value is None:
        return None
    sql, out, i = str(value), [], 0
    while i < len(sql):
        if sql[i].isspace():
            i += 1
            continue
        if sql[i] in ("'", '"'):
            quote, start = sql[i], i
            i += 1
            while i < len(sql):
                if sql[i] == quote:
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                if sql[i] == '\\' and quote == "'" and start > 0 and sql[start - 1] in 'Ee':
                    i += 2
                else:
                    i += 1
            else:
                raise ValueError('Unterminated native SQL literal')
            token = sql[start:i]
            if quote == '"' and token == q(schema) and sql[i:i+1] == '.':
                i += 1
                continue
            # A serial default can deparse its local sequence as a regclass
            # string. Only this proven cast may normalize a schema in a string.
            if quote == "'" and token.startswith("'" + schema + '.') and re.match(r'\s*::\s*regclass\b', sql[i:]):
                token = "'" + token[len(schema) + 2:]
            out.append(token)
        elif sql[i].isalpha() or sql[i] == '_':
            start = i
            i += 1
            while i < len(sql) and (sql[i].isalnum() or sql[i] in '_$'):
                i += 1
            token = sql[start:i]
            if token == schema and sql[i:i+1] == '.':
                i += 1
                continue
            out.append(token.lower())
        elif sql[i] == '$':
            marker = re.match(r'\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$', sql[i:])
            if not marker:
                raise ValueError('Unsupported native SQL dollar token')
            end = sql.find(marker.group(), i + len(marker.group()))
            if end < 0:
                raise ValueError('Unterminated native SQL dollar literal')
            out.append(sql[i:end + len(marker.group())])
            i = end + len(marker.group())
        else:
            out.append(sql[i])
            i += 1
    return out


def _qualified(namespace, name, local_schema):
    return {'schema': '$local' if namespace == local_schema else namespace, 'name': name}


def native_schema(connection, schema):
    """Read structural pg_catalog facts, without evaluating application SQL."""
    relations = _fetch(connection, '''
        SELECT c.oid,c.relname,c.relkind,c.relpersistence,c.relispartition,
               c.relrowsecurity,c.relforcerowsecurity,c.reloptions
          FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname=%s ORDER BY c.relname''', (schema,))
    tables, identities, extra = {}, {}, []
    for oid, name, kind, persistence, partition, row_security, force_rls, options in relations:
        identities[name] = int(oid)
        if kind in ('i', 'I', 'S'):
            continue
        if kind != 'r' or partition:
            extra.append({'kind': kind, 'name': name, 'partition': bool(partition)})
            continue
        columns = {}
        attnames = {}
        for row in _fetch(connection, '''
            SELECT a.attnum,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),
                   a.attnotnull,a.attidentity,a.attgenerated,
                   pg_catalog.pg_get_expr(d.adbin,d.adrelid,false),
                   cn.nspname,co.collname,a.attislocal,a.attinhcount,a.attacl
              FROM pg_catalog.pg_attribute a
              LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
              LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation
              LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid=co.collnamespace
             WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', (oid,)):
            number, column, declared, notnull, identity, generated, default, cn, collate, local, inherited, acl = row
            attnames[int(number)] = column
            columns[column] = {'type': declared, 'not_null': bool(notnull), 'identity': identity,
                'generated': generated, 'default': _expression(default, schema),
                'collation': _qualified(cn, collate, schema) if collate else None,
                'local': bool(local), 'inherited_count': inherited,
                'column_acl': sorted(acl) if acl else []}
        constraints = []
        for row in _fetch(connection, '''
            SELECT c.contype,c.condeferrable,c.condeferred,c.convalidated,c.connoinherit,
                   pg_catalog.pg_get_constraintdef(c.oid,false),
                   rn.nspname,rc.relname,c.conkey,c.confkey,c.confupdtype,c.confdeltype,c.confmatchtype,
                   c.conislocal,c.coninhcount
              FROM pg_catalog.pg_constraint c
              LEFT JOIN pg_catalog.pg_class rc ON rc.oid=c.confrelid
              LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid=rc.relnamespace
             WHERE c.conrelid=%s ORDER BY c.oid''', (oid,)):
            typ, deferrable, deferred, validated, noinherit, definition, ns, target, keys, target_keys, update, delete, match, local, inherited = row
            if typ not in ('p', 'u', 'f', 'c', 'x', 'n'):
                raise ValueError('Unsupported native constraint type')
            referenced = None
            if target:
                target_columns = dict(_fetch(connection, '''
                    SELECT a.attnum,a.attname FROM pg_catalog.pg_attribute a
                    JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped''', (ns, target)))
                referenced = {**_qualified(ns, target, schema),
                              'columns': [target_columns[int(k)] for k in (target_keys or [])]}
            constraints.append({'type': typ, 'definition': _expression(definition, schema),
                'columns': [attnames[int(k)] for k in (keys or [])], 'references': referenced,
                'deferrable': bool(deferrable), 'initially_deferred': bool(deferred),
                'validated': bool(validated), 'no_inherit': bool(noinherit),
                'on_update': update, 'on_delete': delete, 'match': match,
                'local': bool(local), 'inherited_count': inherited})
        indexes = []
        for row in _fetch(connection, '''
            SELECT i.indexrelid,am.amname,i.indisunique,i.indisprimary,i.indisexclusion,
                   i.indimmediate,i.indisvalid,i.indisready,i.indislive,
                   i.indnatts,i.indnkeyatts,i.indkey::smallint[],i.indclass::oid[],
                   i.indcollation::oid[],i.indoption::smallint[],
                   pg_catalog.pg_get_expr(i.indexprs,i.indrelid,false),
                   pg_catalog.pg_get_expr(i.indpred,i.indrelid,false),
                   COALESCE((to_jsonb(i)->>'indnullsnotdistinct')::boolean,false),ic.reloptions
              FROM pg_catalog.pg_index i
              JOIN pg_catalog.pg_class ic ON ic.oid=i.indexrelid
              JOIN pg_catalog.pg_am am ON am.oid=ic.relam
             WHERE i.indrelid=%s ORDER BY i.indexrelid''', (oid,)):
            ix, method, unique, primary, exclusion, immediate, valid, ready, live, total, keycount, keys, classes, collations, flags, expressions, predicate, nulls_not_distinct, ix_options = row
            terms = [_expression(_one(connection, 'SELECT pg_catalog.pg_get_indexdef(%s,%s,false)', (ix, position))[0], schema)
                     for position in range(1, int(total) + 1)]
            operators = []
            for op in classes:
                ns, op_name = _one(connection, '''SELECT n.nspname,c.opcname FROM pg_catalog.pg_opclass c
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.opcnamespace WHERE c.oid=%s''', (op,))
                operators.append(_qualified(ns, op_name, schema))
            normalized_collations = []
            for collate in collations:
                if not collate:
                    normalized_collations.append(None)
                else:
                    ns, col_name = _one(connection, '''SELECT n.nspname,c.collname FROM pg_catalog.pg_collation c
                        JOIN pg_catalog.pg_namespace n ON n.oid=c.collnamespace WHERE c.oid=%s''', (collate,))
                    normalized_collations.append(_qualified(ns, col_name, schema))
            indexes.append({'method': method, 'unique': bool(unique), 'primary': bool(primary),
                'exclusion': bool(exclusion), 'immediate': bool(immediate), 'valid': bool(valid),
                'ready': bool(ready), 'live': bool(live), 'key_count': keycount,
                'columns': [attnames[int(k)] if k else None for k in keys], 'terms': terms,
                'operator_classes': operators, 'collations': normalized_collations,
                'flags': list(flags), 'expressions': _expression(expressions, schema),
                'predicate': _expression(predicate, schema), 'nulls_not_distinct': bool(nulls_not_distinct),
                'options': sorted(ix_options or [])})
        triggers = [_expression(row[0], schema) for row in _fetch(connection,
            'SELECT pg_catalog.pg_get_triggerdef(oid,false) FROM pg_catalog.pg_trigger WHERE tgrelid=%s AND NOT tgisinternal ORDER BY oid', (oid,))]
        policies = _fetch(connection, '''SELECT p.polname,p.polcmd,p.polpermissive,p.polroles::oid[],
            pg_catalog.pg_get_expr(p.polqual,p.polrelid,false),pg_catalog.pg_get_expr(p.polwithcheck,p.polrelid,false)
            FROM pg_catalog.pg_policy p WHERE p.polrelid=%s ORDER BY p.polname''', (oid,))
        rules = [_expression(row[0], schema) for row in _fetch(connection,
            'SELECT pg_catalog.pg_get_ruledef(oid,false) FROM pg_catalog.pg_rewrite WHERE ev_class=%s ORDER BY oid', (oid,))]
        tables[name] = {'columns': columns, 'persistence': persistence, 'row_security': bool(row_security),
            'force_row_security': bool(force_rls), 'options': sorted(options or []),
            'constraints': sorted(constraints, key=lambda v: json.dumps(v, sort_keys=True)),
            'indexes': sorted(indexes, key=lambda v: json.dumps(v, sort_keys=True)),
            'user_triggers': triggers, 'policies': [list(row) for row in policies], 'rules': rules}
    sequences = []
    for row in _fetch(connection, '''
        SELECT c.relname,pg_catalog.format_type(s.seqtypid,NULL),s.seqstart,s.seqincrement,
               s.seqmax,s.seqmin,s.seqcache,s.seqcycle,tn.nspname,t.relname,a.attname,d.deptype
          FROM pg_catalog.pg_sequence s
          JOIN pg_catalog.pg_class c ON c.oid=s.seqrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          LEFT JOIN pg_catalog.pg_depend d ON d.classid='pg_catalog.pg_class'::regclass
               AND d.objid=s.seqrelid AND d.refclassid='pg_catalog.pg_class'::regclass AND d.deptype IN ('a','i')
          LEFT JOIN pg_catalog.pg_class t ON t.oid=d.refobjid
          LEFT JOIN pg_catalog.pg_namespace tn ON tn.oid=t.relnamespace
          LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
         WHERE n.nspname=%s ORDER BY c.relname''', (schema,)):
        name, typ, start, increment, maximum, minimum, cache, cycle, owner_schema, owner_table, owner_column, dependency = row
        sequences.append({'name': name, 'type': typ, 'start': start, 'increment': increment,
            'maximum': maximum, 'minimum': minimum, 'cache': cache, 'cycle': bool(cycle),
            'owner': {**_qualified(owner_schema, owner_table, schema), 'column': owner_column} if owner_table else None,
            'dependency': dependency})
    return {'tables': tables, 'sequences': sequences, 'extra': extra, 'object_identity': identities}


def inspect_postgres(connection, *, django_config, owned_guard):
    """Inspect only a registry-owned bos_verify target; never a working DB.

    django_config is an explicit Django PostgreSQL DATABASE config for the same
    just-created database. It is never reconstructed from a DSN or printed.
    A separate unique alias creates the reference schema. Cleanup uses RESTRICT,
    never CASCADE or DROP DATABASE, and only after namespace OID/owner proof.
    """
    from scripts.data_transfer import ConnectionOwnership
    from scripts.schema_preflight import expected_schema, stable_sha
    result = {'schema': 1, 'backend': 'postgresql', 'complete': False, 'can_migrate': False,
              'profile': 'unknown', 'known_migrations': False, 'findings': [], 'tables': {},
              'runtime_proof': 'not_run', 'reference_schema_removed': False}
    findings, alias, db = result['findings'], None, None
    alias_registered = False
    reference, ownership, actual_before = None, None, None
    applied_rows = None
    expected_table_names = set()
    phase = 'ownership'
    try:
        if type(owned_guard) is not ConnectionOwnership:
            raise ValueError('A minted ConnectionOwnership capability is required')
        name = ConnectionOwnership.assert_owned(owned_guard, connection)
        if not re.fullmatch(r'bos_verify_[0-9a-f]{16}', name) or not connection.autocommit:
            raise ValueError('Target must be an idle owned disposable PostgreSQL database')
        if getattr(getattr(connection, 'info', None), 'transaction_status', None) != 0:
            raise ValueError('Target connection must have no pending transaction')
        identity = _one(connection, '''SELECT current_database(),current_user,current_setting('server_version'),
            current_setting('server_version_num')::integer,current_setting('server_encoding'),
            inet_server_addr()::text,inet_server_port(),pg_postmaster_start_time(),
            (SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database())''')
        if identity[0] != name or identity[4] != 'UTF8' or identity[3] < 140000:
            raise ValueError('Unsupported actual PostgreSQL target identity/profile')
        result['runtime_proof'] = {'vendor': 'postgresql', 'server_version': identity[2],
                                   'database': name, 'owned_capability': True}
        config = deepcopy(django_config)
        if config.get('ENGINE') != 'django.db.backends.postgresql' or config.get('NAME') != name:
            raise ValueError('Explicit Django configuration must name the same owned PostgreSQL target')
        # Do not derive credentials or second-connection parameters from raw DSN.
        if not all(key in config for key in ('USER', 'PASSWORD', 'HOST', 'PORT')):
            raise ValueError('Explicit Django connection parameters are required')
        phase = 'public_catalog'
        actual_before = native_schema(connection, 'public')
        result['actual_schema'] = actual_before
        result['postgres_schema_hash'] = stable_sha(actual_before)
        foreign_schemas = [row[0] for row in _fetch(connection,
            "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname !~ '^pg_' ORDER BY nspname")]
        if foreign_schemas:
            findings.append({'code': 'unknown_postgres_schemas', 'schemas': foreign_schemas})
        if actual_before['extra']:
            findings.append({'code': 'unsupported_postgres_relation', 'relations': actual_before['extra']})
        if 'django_migrations' not in actual_before['tables']:
            raise ValueError('Migration recorder is absent')
        applied_rows = _fetch(connection, 'SELECT app,name FROM public.django_migrations ORDER BY app,name')
        applied = set(applied_rows)
        if len(applied) != len(applied_rows):
            findings.append({'code': 'duplicate_migration_record'})
        from django.apps import apps
        from django.conf import settings
        from django.db import connections
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.recorder import MigrationRecorder
        from django.db.migrations.state import ProjectState
        if not apps.ready:
            raise ValueError('Django must use the reviewed project profile')
        loader = MigrationLoader(None, ignore_no_migrations=True)
        unknown = applied - set(loader.disk_migrations)
        result['known_migrations'] = not unknown
        if unknown:
            findings.append({'code': 'unknown_migrations', 'migrations': sorted(unknown)})
            return result
        unavailable = applied - set(loader.graph.nodes)
        if unavailable:
            findings.append({'code': 'unsupported_replaced_migration_profile', 'migrations': sorted(unavailable)})
            return result
        missing = {parent.key for node in applied for parent in loader.graph.node_map[node].parents if parent.key not in applied}
        if missing:
            findings.append({'code': 'inconsistent_migration_history', 'missing_dependencies': sorted(missing)})
            return result
        heads = sorted(node for node in applied if not any(child.key in applied for child in loader.graph.node_map[node].children))
        state = loader.project_state(nodes=heads) if applied else ProjectState(real_apps=loader.unmigrated_apps)
        sqlite_expected, extras, descriptors, unmanaged = expected_schema(state)
        if extras:
            findings.append({'code': 'unsupported_logical_schema_objects'})
        result['tables'] = descriptors
        result['configured_profile'] = {'use_tz': bool(settings.USE_TZ), 'time_zone': settings.TIME_ZONE}
        for table, descriptor in descriptors.items():
            for column in descriptor['columns']:
                if column['kind'] is None:
                    findings.append({'code': 'unsupported_field_kind', 'table': table, 'column': column['name']})
        models = [m for m in state.apps.get_models(include_auto_created=True, include_swapped=True)
                  if not m._meta.swapped and m._meta.managed]
        models.append(MigrationRecorder.Migration)
        expected_table_names = {m._meta.db_table for m in models}
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) for name in expected_table_names):
            raise ValueError('Schema-qualified/custom model tables require a reviewed reference adapter')
        if any(m._meta.db_tablespace or any(f.db_tablespace for f in m._meta.local_fields) for m in models):
            raise ValueError('Custom tablespaces require a reviewed reference adapter')
        phase = 'reference_connection'
        alias = 'bos_schema_reference_' + uuid4().hex
        reference = alias
        if alias in connections.databases:
            raise ValueError('Reference connection alias unexpectedly exists')
        config.update(CONN_MAX_AGE=0, CONN_HEALTH_CHECKS=False, AUTOCOMMIT=True,
                      ATOMIC_REQUESTS=False, TIME_ZONE=None, TEST={})
        config.setdefault('OPTIONS', {})
        connections.databases[alias] = config
        alias_registered = True
        db = connections[alias]
        db.ensure_connection()
        second = _one(db, '''SELECT current_database(),current_user,current_setting('server_version'),
            current_setting('server_version_num')::integer,current_setting('server_encoding'),
            inet_server_addr()::text,inet_server_port(),pg_postmaster_start_time(),
            (SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database())''')
        if second != identity:
            raise ValueError('Reference connection resolved to a different PostgreSQL instance/identity')
        phase = 'reference_create'
        result['reference_schema'] = {'name': reference, 'created': False}
        with db.cursor() as cursor:
            cursor.execute('CREATE SCHEMA ' + q(reference) + ' AUTHORIZATION CURRENT_USER')
        result['reference_schema']['created'] = True
        ownership = _one(db, 'SELECT oid,nspowner FROM pg_catalog.pg_namespace WHERE nspname=%s', (reference,))
        result['reference_schema'].update(oid=ownership[0], owner_oid=ownership[1])
        with db.cursor() as cursor:
            cursor.execute('SET search_path TO ' + q(reference) + ', pg_catalog')
        phase = 'reference_schema_editor'
        with db.schema_editor() as editor:
            for model in sorted(models, key=lambda m: m._meta.db_table):
                if not model._meta.auto_created:
                    editor.create_model(model)
        phase = 'native_compare'
        expected = native_schema(db, reference)
        result['expected_schema'] = expected
        for table in sorted(set(expected['tables']) - set(actual_before['tables'])):
            findings.append({'code': 'missing_table', 'table': table})
        for table in sorted(set(actual_before['tables']) - set(expected['tables'])):
            findings.append({'code': 'unmanaged_table' if table in unmanaged else 'unknown_table', 'table': table})
        for table in sorted(set(actual_before['tables']) & set(expected['tables'])):
            for component in expected['tables'][table]:
                if actual_before['tables'][table][component] != expected['tables'][table][component]:
                    findings.append({'code': 'native_' + component + '_mismatch', 'table': table,
                        'actual': actual_before['tables'][table][component], 'expected': expected['tables'][table][component]})
        if actual_before['sequences'] != expected['sequences']:
            findings.append({'code': 'native_sequence_schema_mismatch', 'actual': actual_before['sequences'], 'expected': expected['sequences']})
        if expected['extra']:
            findings.append({'code': 'unsupported_reference_relation', 'relations': expected['extra']})
        result['profile'] = 'latest' if applied == set(loader.graph.nodes) else 'historical'
        migration_state = {'applied': sorted(applied), 'targets': heads, 'latest': sorted(loader.graph.leaf_nodes())}
        # Identical logical state hash to SQLite, not a false equivalence of SQL.
        migration_state['hash'] = stable_sha({'applied': sorted(applied), 'tables': descriptors, 'expected_schema': sqlite_expected})
        result['migration_state'] = migration_state
        result['migration_state_hash'] = migration_state['hash']
    except Exception as exc:
        # Raw connection errors can include DSN parameters. Never serialize them.
        findings.append({'code': 'postgres_schema_inspection_error', 'phase': phase, 'error_type': type(exc).__name__})
    finally:
        if db is not None and ownership is not None:
            try:
                db.rollback()
                db.set_autocommit(True)
                current_owner = _one(db, 'SELECT oid,nspowner FROM pg_catalog.pg_namespace WHERE nspname=%s', (reference,))
                if tuple(current_owner) != tuple(ownership):
                    raise ValueError('Reference namespace ownership changed; no cleanup is permitted')
                present = _fetch(db, '''SELECT c.relname,c.relkind FROM pg_catalog.pg_class c
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s ORDER BY c.relname''', (reference,))
                tables = [name for name, kind in present if kind == 'r']
                if any(kind not in ('r', 'i', 'S') for _, kind in present) or not set(tables) <= expected_table_names:
                    raise ValueError('Unexpected reference objects; refuse broad cleanup')
                with db.cursor() as cursor:
                    if tables:
                        # One explicit drop set permits internal FKs, while an
                        # external dependency blocks RESTRICT instead of falling.
                        cursor.execute('DROP TABLE ' + ','.join(q(reference) + '.' + q(name) for name in tables) + ' RESTRICT')
                    cursor.execute('DROP SCHEMA ' + q(reference) + ' RESTRICT')
                result['reference_schema_removed'] = True
            except Exception as exc:
                findings.append({'code': 'owned_reference_cleanup_failed', 'error_type': type(exc).__name__})
        if db is not None:
            db.close()
        if alias_registered:
            from django.db import connections
            try:
                del connections[alias]
            except AttributeError:
                pass
            connections.databases.pop(alias, None)
        if actual_before is not None:
            try:
                ConnectionOwnership.assert_owned(owned_guard, connection)
                after = native_schema(connection, 'public')
                result['source_unchanged'] = stable_sha(actual_before) == stable_sha(after)
                if not result['source_unchanged']:
                    findings.append({'code': 'public_schema_changed_during_inspection'})
                if applied_rows is not None:
                    recorder_after = _fetch(connection, 'SELECT app,name FROM public.django_migrations ORDER BY app,name')
                    if recorder_after != applied_rows:
                        findings.append({'code': 'migration_recorder_changed_during_inspection'})
                unexpected_schemas = [row[0] for row in _fetch(connection,
                    "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname !~ '^pg_' ORDER BY nspname")
                    if row[0] != reference]
                if unexpected_schemas:
                    findings.append({'code': 'unknown_postgres_schemas_after_inspection', 'schemas': unexpected_schemas})
            except Exception as exc:
                findings.append({'code': 'public_schema_recheck_failed', 'error_type': type(exc).__name__})
    result['complete'] = result['can_migrate'] = not findings and bool(result['tables']) and result['reference_schema_removed']
    return result
