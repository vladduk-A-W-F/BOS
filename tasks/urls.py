from rest_framework.routers import DefaultRouter
from .views import TaskViewSet

# Router automatically creates all URL patterns for the ViewSet:
# GET  /api/tasks/       — list all tasks
# POST /api/tasks/       — create a task
# GET  /api/tasks/1/     — get task with id=1
# PUT  /api/tasks/1/     — replace task 1 fully
# PATCH /api/tasks/1/    — update task 1 partially
# DELETE /api/tasks/1/   — delete task 1
router = DefaultRouter()
router.register(r'tasks', TaskViewSet)

urlpatterns = router.urls
