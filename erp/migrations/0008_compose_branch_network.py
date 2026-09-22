from django.db import migrations
from erp.migration_operations_v1 import AssertComposedNetworkSchema


class Migration(migrations.Migration):
    dependencies = [('erp', '0006_branch_links'), ('erp', '0007_request_timing')]
    operations = [AssertComposedNetworkSchema()]
