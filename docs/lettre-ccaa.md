QUANTUM TECHNOLOGIES SAS
Plateforme MAPNET — Cartographie collaborative et conformité aérienne
Yaoundé, Cameroun

Objet : Demande d'agrément et présentation du dispositif de conformité géospatiale
        pour l'exploitation de drones de cartographie sur le territoire camerounais

À l'attention de :
Cameroon Civil Aviation Authority (CCAA / Autorité Aéronautique du Cameroun)
Direction de la Sécurité et de la Navigation Aérienne

Yaoundé, le 17 juillet 2026

Madame, Monsieur,

Dans le cadre du déploiement de la plateforme MAPNET, destinée à enrichir la
cartographie routière du Cameroun à partir de traces GPS collectées auprès des
conducteurs de mototaxis (bendskin) et de taxis, la société Quantum Technologies
SAS sollicite l'agrément de son dispositif de vérification automatique de
conformité aérienne pour les opérations de collecte par aéronefs télépilotés
(drones).

1. OBJET DU DISPOSITIF

MAPNET intègre un service de conformité (« ccaa-compliance ») qui vérifie, avant
toute autorisation de vol, que le plan de vol soumis ne pénètre aucune zone
d'exclusion aérienne (no-fly zone) définie par l'autorité. Le contrôle est
automatique, tracé et horodaté.

2. ZONES D'EXCLUSION PRISES EN COMPTE

Le référentiel géospatial embarque notamment :
 - l'Aéroport international de Yaoundé Nsimalen (zone aéroportuaire, plafond 0 m) ;
 - les zones sensibles complémentaires fournies au format GeoJSON, mises à jour
   sur instruction de la CCAA.

3. FONCTIONNEMENT VÉRIFIABLE

Pour chaque demande, l'opérateur transmet : identifiant du drone, identifiant de
l'opérateur, altitude prévue, créneau horaire, et le polygone de vol (GeoJSON).
Le service calcule l'intersection géométrique entre le polygone de vol et les
zones d'exclusion (PostGIS / analyse spatiale) et retourne une décision :
 - REJETÉ si intersection avec une zone d'exclusion, avec le détail de la zone
   en conflit ;
 - APPROUVÉ en l'absence de conflit.

Preuves de fonctionnement (tests réels réalisés sur l'infrastructure) :
 - Plan de vol situé dans l'emprise de l'aéroport de Nsimalen :
       => décision « rejected », conflit signalé
          « Aéroport international de Yaoundé Nsimalen » (type airport).
 - Plan de vol situé à Douala, hors de toute zone :
       => décision « approved », aucun conflit.

4. TRAÇABILITÉ

Chaque plan de vol soumis est enregistré (opérateur, drone, polygone, horodatage,
décision) et consultable, garantissant l'auditabilité des autorisations.

5. ENGAGEMENT

Quantum Technologies SAS s'engage à intégrer sans délai toute mise à jour des
zones d'exclusion communiquée par la CCAA, et à suspendre toute opération sur
demande de l'autorité.

Nous restons à votre disposition pour une démonstration technique du dispositif
et pour tout complément d'information.

Veuillez agréer, Madame, Monsieur, l'expression de notre haute considération.

Pour Quantum Technologies SAS
La Direction Technique — Projet MAPNET
