from django.urls import path
from . import views, import_views, correction_views
urlpatterns=[path('workpoints/', views.workpoints, name='bos-workpoints')]
urlpatterns += [path('orders/<int:pk>/settlement/', views.order_settlement, name='bos-order-settlement'),
                path('lines/<int:pk>/supply-options/', views.supply_options, name='bos-supply-options')]
urlpatterns += [path('purchases/<int:pk>/document-match/', views.document_match, name='bos-document-match')]
urlpatterns += [path('orders/<int:pk>/trace/',views.order_trace,name='bos-order-trace'),path('corrections/outcome/',correction_views.outcome,name='bos-correction-outcome'),path('import/preview/',import_views.preview,name='bos-import-preview'),path('import/template/',import_views.template,name='bos-import-template'),path('import/batches/<uuid:batch_id>/',import_views.batch_detail,name='bos-import-batch'),path('import/batches/<uuid:batch_id>/export/',import_views.export,name='bos-import-export'),path('orders/<int:pk>/next/',views.next_action),path('snapshot/',views.snapshot),path('preview/',views.preview),path('export/',views.export),path('changes/<int:pk>/impact/',views.change_impact),path('orders/<int:pk>/draft/',views.draft)]

from . import network_views, module_views
urlpatterns_network=[path('network/',network_views.snapshot,name='bos-network'),path('network/export/',network_views.export,name='bos-network-export')]
urlpatterns += urlpatterns_network
urlpatterns += [path('modules/',module_views.registry,name='bos-modules')]

from . import monitoring_views
urlpatterns += [path('monitoring/', monitoring_views.overview, name='bos-monitoring'),
                path('monitoring/query/<slug:key>/', monitoring_views.standard_query, name='bos-monitoring-query')]
