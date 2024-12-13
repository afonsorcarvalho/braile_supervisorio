
# -*- coding: utf-8 -*-
{
    'name': 'Supervisorio Braile',
    'version': '1.0',
    'summary': 'Supervisório esterilização quimica, estufa',
    'description': 'Descrição detalhada do módulo',
    'author': 'Afonso Carvalho',
    'depends': ['steril_supervisorio'],
    'sequence':-1,
    "qweb": [
        
    ],
    'data': [
       
        'security/ir.model.access.csv',
        'views/supervisorio_ciclo_views.xml',
        'reports/braile_supervisorio_ciclo_reports_template.xml',
        'reports/braile_supervisorio_ciclo_reports.xml',
       
    ],
    
    'assets':{
        'web.assets_backend':[
         

        ],

    },
    'installable': True,
    'application': True,
}
