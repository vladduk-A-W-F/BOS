"""Only fresh synthetic reference rows; business writers belong to HTTP APIs."""
from copy import deepcopy


def bootstrap(expected, http, check):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from django.test import Client
    from employees.models import Employee
    from finance.models import Counterparty
    from operations.models import Configuration, Document
    from erp.models import Item, Location

    identities, clients, aliases, proof = {}, {}, {}, []
    Configuration.objects.create(key='dataset', value={
        'as_of': expected['numeric_oracle']['as_of'],
        'name': 'Gate 6 — explicitly synthetic empty company', 'synthetic': True})
    for row in expected['bootstrap']['users']:
        role = row['group']
        user = get_user_model().objects.create_user(
            username=row['username'], password='gate6-synthetic-login-only')
        user.groups.set([Group.objects.get_or_create(name=role)[0]])
        for codename in ('view_document', 'download_document', 'export_workspace'):
            user.user_permissions.add(Permission.objects.get(
                content_type__app_label='operations', content_type__model='document', codename=codename))
        client = Client(enforce_csrf_checks=True)
        http(client, 'GET', '/api/auth/csrf/')
        http(client, 'POST', '/api/auth/login/', {
            'username': user.username, 'password': 'gate6-synthetic-login-only'})
        check('Actual HTTP login: ' + role, client.session.get('_auth_user_id') == str(user.pk))
        clients[role], identities[role] = client, user
        aliases[row['employee_alias']] = None
    for row in expected['bootstrap']['employees']:
        user = get_user_model().objects.get(username=row['user_username'])
        employee = Employee.objects.create(full_name=row['full_name'], user=user,
            role='Керівник' if row['alias']=='ceo_employee' else 'Менеджер', department='E2E')
        aliases[row['alias']] = employee.pk
    for row in expected['bootstrap']['counterparties']:
        partner = Counterparty.objects.create(name=row['name'], type=row['type'])
        aliases[row['alias']] = partner.pk
        aliases[row['external_code']] = partner.pk
    for doc in expected['source_documents']:
        if doc['creation_phase'] != 'bootstrap':
            continue
        source = http.upload(clients['ceo'], doc, statement=False)
        # Accepted bootstrap-only classification: generic upload deliberately
        # does not accept arbitrary access labels. Original bytes stay untouched.
        Document.objects.filter(pk=source['id']).update(access_level='operational')
        check('Explicit operational reference classification: ' + doc['code'],
              Document.objects.get(pk=source['id']).access_level == doc['access_level'])
        aliases[doc['code']] = source['id']
        proof.append({'code':doc['code'], 'document_id':source['id'],
            'classification':'operational', 'classification_phase':'bootstrap_before_baseline',
            'upload':'actual_private_HTTP', 'review':'actual_HTTP',
            'original_bytes':'actual_HTTP_download_SHA256', 'sha256':doc['sha256']})
    item = deepcopy(expected['bootstrap']['item'])
    item['document_id'] = aliases[item.pop('document_code')]
    aliases['item'] = Item.objects.create(**item).pk
    for location in expected['bootstrap']['locations']:
        aliases[location['code']] = Location.objects.create(**location).pk
    return clients, identities, aliases, proof
