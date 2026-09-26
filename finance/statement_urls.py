from django.urls import path
from . import statement_views as v
urlpatterns=[
    path('sources/',v.sources,name='statement-source'),
    path('imports/',v.imports,name='statement-imports'),
    path('imports/<uuid:pk>/',v.import_detail,name='statement-import-detail'),
    path('imports/<uuid:pk>/export/',v.export,name='statement-export'),
    path('lines/',v.lines,name='statement-lines'),
    path('lines/<uuid:pk>/',v.line_detail,name='statement-line-detail'),
    path('lines/<uuid:pk>/candidates/',v.candidates,name='statement-candidates'),
    path('summary/',v.summary,name='statement-summary')]
