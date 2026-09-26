from rest_framework import serializers
from .models import Task
from .queries import project

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model=Task
        fields=['id','title','priority','status','assignee','deadline','category','branch','created_at','assignee_employee','sales_order','result','archived_at']
        read_only_fields=fields
    def to_representation(self,instance):return project(instance)
