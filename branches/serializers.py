from rest_framework import serializers
from .models import Branch

# Порядок типов в дереве: сверху центр, снизу периферия.
# Meta.ordering модели алфавитный по type ('foreign' < 'headquarters'),
# что выдало бы иностранные филии впереди центрального офиса.
TYPE_ORDER = ['headquarters', 'department', 'regional', 'mobile', 'foreign']


def ordered(queryset_or_list):
    """Узлы одного уровня: сначала по типу, внутри типа — по имени."""
    return sorted(
        queryset_or_list,
        key=lambda b: (TYPE_ORDER.index(b.type) if b.type in TYPE_ORDER else len(TYPE_ORDER),
                       b.name),
    )


class BranchSerializer(serializers.ModelSerializer):
    """Плоский вид узла — то, что фронт кладёт в branchMap (карта, дерево)."""

    class Meta:
        model = Branch
        fields = ['id', 'code', 'name', 'short_name', 'type', 'parent', 'lat', 'lng',
                  'status', 'employee_count', 'created_at']


class BranchTreeSerializer(BranchSerializer):
    """Рекурсивный вид — /api/branches/ отдаёт дерево, фронт его расплющивает.

    Дерево (а не плоский список) нужно, чтобы сайдбар не восстанавливал
    иерархию по parent_id вручную — порядок и вложенность приходят готовыми.
    """
    children = serializers.SerializerMethodField()

    class Meta(BranchSerializer.Meta):
        fields = BranchSerializer.Meta.fields + ['children']

    def get_children(self, obj):
        return BranchTreeSerializer(ordered(obj.children.all()), many=True,
                                    context=self.context).data
