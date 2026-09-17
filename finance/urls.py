from rest_framework.routers import DefaultRouter
from .views import CounterpartyViewSet, ContractViewSet, TransactionViewSet, SalaryViewSet

router = DefaultRouter()
router.register(r'counterparties', CounterpartyViewSet)
router.register(r'contracts', ContractViewSet)
router.register(r'transactions', TransactionViewSet)
router.register(r'salaries', SalaryViewSet)

urlpatterns = router.urls
