from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet

# DefaultRouter auto-generates all CRUD URLs from the ViewSet:
#   /employees/      → list + create
#   /employees/{id}/ → retrieve + update + delete
router = DefaultRouter()
router.register(r'employees', EmployeeViewSet)

urlpatterns = router.urls
