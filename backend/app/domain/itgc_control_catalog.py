from __future__ import annotations

# Kept as plain dicts so both deterministic composer and LLM prompts can reuse it
# without importing report output models (avoids circular imports).
#
# IMPORTANT:
# This catalog is aligned with the control reference semantics used by the project's
# Excel input template / datasets (e.g., Meridia FY2025 sample), not a generic ITGC
# library. If a future mission uses a different mapping, prefer keyword-based logic
# in the composer to avoid title/reco mismatches.

PROCESS_LABELS: dict[str, str] = {
    "APD": "Gestion des accès",
    "PC": "Gestion des changements",
    "CO": "Exploitation informatique",
}

CONTROL_CATALOG: dict[str, dict[str, str]] = {
    # APD - Gestion des accès
    "APD-01": {
        "process": "APD",
        "description": "Les accès des utilisateurs quittant l’entité (départ, mobilité) sont révoqués en temps opportun sur les applications et infrastructures du périmètre.",
        "test_procedure": "Rapprocher les mouvements RH (départs) avec les comptes actifs et vérifier la désactivation effective, la traçabilité et la gestion des exceptions.",
        "risk_guidance": "Accès non autorisé via des comptes actifs post-départ, pouvant entraîner fuite de données, fraude et atteinte à la confidentialité.",
        "recommendation_guidance": "Mettre en place un workflow RH/IT de désactivation automatique (ou immédiate), suivre les exceptions et réaliser un contrôle de complétude périodique.",
    },
    "APD-02": {
        "process": "APD",
        "description": "Les droits d’accès aux applications, systèmes d’exploitation et bases de données sont désactivés en temps opportun à la suite du départ ou de la mobilité d’un collaborateur.",
        "test_procedure": "Rapprocher les mouvements RH avec les comptes actifs et vérifier la désactivation effective, la traçabilité et le traitement des exceptions sur les différentes couches techniques.",
        "risk_guidance": "Maintien d’accès pour des employés ou prestataires ayant quitté l’organisation, exposant l’entité à des accès non autorisés et à un risque de fraude ou de fuite de données.",
        "recommendation_guidance": "Formaliser et automatiser le processus de révocation des accès à la suite des départs, avec rapprochement RH/IT et revue périodique des comptes actifs.",
    },
    "APD-03": {
        "process": "APD",
        "description": "Les comptes à droits étendus, génériques, partagés ou techniques sont strictement limités, justifiés et font l’objet d’une supervision périodique des usages.",
        "test_procedure": "Identifier les comptes à privilèges élevés, génériques ou partagés, vérifier leur justification, la traçabilité individuelle des actions et la supervision régulière des activités.",
        "risk_guidance": "Utilisation non supervisée de comptes privilégiés ou partagés, rendant difficile l’attribution des actions et augmentant le risque de fraude, d’altération ou d’accès non autorisé.",
        "recommendation_guidance": "Réduire l’usage des comptes partagés et privilégiés, mettre en place des comptes nominatifs, renforcer la journalisation et formaliser une supervision périodique.",
    },
    "APD-04": {
        "process": "APD",
        "description": "Les droits d’accès font l’objet d’une recertification périodique formelle, permettant de confirmer leur adéquation avec les fonctions exercées.",
        "test_procedure": "Vérifier l’existence, la périodicité et la traçabilité des campagnes de recertification, ainsi que la remédiation des droits excessifs ou incompatibles.",
        "risk_guidance": "Maintien de droits excessifs, incompatibles ou injustifiés, augmentant le risque d’erreur, de fraude et d’accès non autorisé aux traitements sensibles.",
        "recommendation_guidance": "Mettre en oeuvre une campagne formelle et périodique de recertification des accès, documenter les validations et corriger les droits incompatibles ou non justifiés.",
    },
    "APD-05": {
        "process": "APD",
        "description": "La politique de sécurité des mots de passe et des mécanismes d’authentification est conforme aux bonnes pratiques et appliquée de manière homogène.",
        "test_procedure": "Comparer les paramètres de mots de passe et de verrouillage aux politiques de sécurité, et vérifier leur application sur les différentes couches techniques.",
        "risk_guidance": "Configuration insuffisante des mots de passe et des mécanismes de verrouillage, favorisant la compromission de comptes et les accès non autorisés.",
        "recommendation_guidance": "Aligner les paramètres de mots de passe sur les bonnes pratiques (longueur, complexité, historique, expiration, verrouillage) et formaliser une revue périodique des configurations.",
    },
    "APD-06": {
        "process": "APD",
        "description": "Les paramètres de mots de passe et d’authentification sont conformes à la politique de sécurité (longueur, complexité, expiration, historique, verrouillage).",
        "test_procedure": "Comparer la configuration réelle des politiques de mots de passe avec la charte/politique de sécurité et vérifier l’application à l’ensemble des comptes.",
        "risk_guidance": "Compromission de comptes (force brute, réutilisation), accès non autorisé et fuite de données.",
        "recommendation_guidance": "Aligner les paramètres sur la politique (longueur/complexité/expiration/historique) et définir une revue périodique des configurations.",
    },
    "APD-07": {
        "process": "APD",
        "description": "Les créations et modifications d’accès font l’objet d’une validation formelle (hiérarchique et applicative) et sont tracées.",
        "test_procedure": "Revoir un échantillon de demandes d’accès et vérifier l’existence d’une double validation, la complétude du dossier et la traçabilité.",
        "risk_guidance": "Octroi d’accès non autorisé ou non justifié, pouvant conduire à des opérations incompatibles ou à des accès excessifs.",
        "recommendation_guidance": "Exiger l’utilisation d’un workflow, bloquer les demandes incomplètes et assurer un contrôle qualité (2e niveau) des validations.",
    },
    "APD-08": {
        "process": "APD",
        "description": "Les accès aux données sensibles (paie, RH, données personnelles) sont strictement restreints aux profils habilités et revus périodiquement.",
        "test_procedure": "Identifier les données sensibles, vérifier les profils ayant accès, la justification fonctionnelle et la revue périodique des accès.",
        "risk_guidance": "Atteinte à la confidentialité, non-conformité réglementaire et risques de fuite/exfiltration de données sensibles.",
        "recommendation_guidance": "Redéfinir les rôles, limiter l’accès au strict besoin, documenter les justifications et instaurer une revue régulière des accès sensibles.",
    },
    "APD-09": {
        "process": "APD",
        "description": "Les accès accordés aux prestataires externes sont encadrés (justification, durée, révocation en fin de contrat) et font l’objet d’une revue périodique.",
        "test_procedure": "Revoir la liste des comptes prestataires, vérifier la validité des contrats, la date de fin, la traçabilité des demandes et la révocation.",
        "risk_guidance": "Accès non autorisé par des tiers (contrats expirés), fuite de données et exposition accrue en cas d’incident.",
        "recommendation_guidance": "Mettre en place une gestion du cycle de vie des comptes prestataires (création/expiration/révocation) et une revue périodique avec rapprochement Achats/RH/IT.",
    },
    # PC - Gestion des changements
    "PC-01": {
        "process": "PC",
        "description": "Les changements en production sont approuvés formellement (CAB/validation), testés et documentés avant déploiement.",
        "test_procedure": "Revoir un échantillon de changements, vérifier l’existence d’une demande, d’une approbation, d’une preuve de test et d’un plan de retour arrière.",
        "risk_guidance": "Changements non contrôlés, incidents en production et altération de l’intégrité des traitements.",
        "recommendation_guidance": "Imposer une validation CAB, une preuve de test/recette et un plan de rollback avant tout déploiement, y compris pour les urgences.",
    },
    "PC-02": {
        "process": "PC",
        "description": "Les environnements de développement, test et production sont séparés et les accès cumulés sont encadrés (SoD, dérogations).",
        "test_procedure": "Vérifier la séparation des environnements et analyser les profils ayant des accès cumulés, ainsi que les contrôles de dérogation.",
        "risk_guidance": "Modification non autorisée en production et contournement des validations de mise en production.",
        "recommendation_guidance": "Restreindre les accès cumulés, formaliser les dérogations et renforcer les contrôles de séparation des tâches.",
    },
    "PC-03": {
        "process": "PC",
        "description": "Les changements font l’objet de tests/recettes formalisés avant mise en production, avec validation des résultats.",
        "test_procedure": "Revoir les PV de recette pour un échantillon de mises à jour et vérifier la validation interne préalable.",
        "risk_guidance": "Déploiement de correctifs non maîtrisés entraînant incidents, indisponibilités et erreurs de traitement.",
        "recommendation_guidance": "Formaliser une procédure de test, exiger un PV de recette signé et interdire les déploiements sans validation préalable.",
    },
    "PC-04": {
        "process": "PC",
        "description": "Les transports et déploiements entre environnements sont tracés, autorisés et exécutés par des comptes habilités, reliés à une demande de changement.",
        "test_procedure": "Rapprocher les journaux de transport/déploiement avec les demandes de changement et vérifier les approbations associées.",
        "risk_guidance": "Changements non autorisés et impossibilité de reconstituer l’historique des mises en production.",
        "recommendation_guidance": "Exiger une demande de changement pour tout transport, limiter l’usage des comptes techniques et renforcer le rapprochement automatique outil de change/journaux de transport.",
    },
    "PC-05": {
        "process": "PC",
        "description": "Les dossiers de changement sont complets (analyse d’impact, plan de rollback, validations), conformément au template et à la politique interne.",
        "test_procedure": "Revoir des dossiers de changement et vérifier la présence des pièces obligatoires et des validations.",
        "risk_guidance": "Déploiements insuffisamment maîtrisés, difficultés de retour arrière et augmentation du risque d’incidents.",
        "recommendation_guidance": "Renforcer la gouvernance documentaire (checklist), exiger l’analyse d’impact, le plan de rollback et la validation métier avant déploiement.",
    },
    "PC-06": {
        "process": "PC",
        "description": "Les accès privilégiés en production (DBA, comptes d’administration) sont nominatifs, contrôlés (PAM) et journalisés, afin d’assurer la traçabilité.",
        "test_procedure": "Identifier les comptes privilégiés partagés, vérifier la justification, la journalisation et les mécanismes de contrôle (coffre-fort, rotation).",
        "risk_guidance": "Actions non traçables en production, contournement des contrôles et risque accru de fraude ou d’altération des données.",
        "recommendation_guidance": "Mettre en place des comptes DBA nominatifs, un coffre-fort/PAM, la rotation des secrets et un suivi des connexions (y compris hors heures ouvrées).",
    },
    "PC-07": {
        "process": "PC",
        "description": "Les changements d’urgence sont encadrés par une procédure dédiée (justification, tests, validation post-déploiement, REX).",
        "test_procedure": "Analyser les changements d’urgence, vérifier la justification, les tests réalisés, le REX et la validation post-intervention.",
        "risk_guidance": "Changements urgents non maîtrisés pouvant provoquer incidents et indisponibilités sans capacité de retour arrière.",
        "recommendation_guidance": "Définir une procédure d’urgence (RACI, rollback, validations) et formaliser systématiquement un dossier post-intervention.",
    },
    # CO - Exploitation informatique
    "CO-01": {
        "process": "CO",
        "description": "Les sauvegardes sont réalisées selon une périodicité définie et des tests de restauration sont effectués et documentés.",
        "test_procedure": "Vérifier la périodicité des sauvegardes, la supervision et la réalisation de tests de restauration avec preuves.",
        "risk_guidance": "Perte de données et indisponibilité prolongée en cas d’incident ou de sinistre.",
        "recommendation_guidance": "Planifier des tests de restauration périodiques, documenter les résultats et traiter les écarts (RPO/RTO) avec actions correctives.",
    },
    "CO-02": {
        "process": "CO",
        "description": "Les incidents sont identifiés, tracés et résolus dans des délais appropriés, avec un pilotage basé sur des SLA et des indicateurs.",
        "test_procedure": "Revoir les tickets d’incidents, les délais de résolution, les escalades et la consolidation des indicateurs de pilotage.",
        "risk_guidance": "Indisponibilité, non-respect des engagements de service et pertes financières / opérationnelles.",
        "recommendation_guidance": "Définir des SLA, renforcer l’utilisation de l’outil de ticketing et consolider un tableau de bord de pilotage (volumétrie, délais, récurrences).",
    },
    "CO-03": {
        "process": "CO",
        "description": "Les prestations IT externalisées font l’objet d’un suivi (SLA/KPI, comités, revues) et d’une contractualisation des exigences de contrôle.",
        "test_procedure": "Vérifier l’existence des SLA/KPI, comités de pilotage, comptes rendus et mécanismes de contrôle des prestataires.",
        "risk_guidance": "Service non maîtrisé, dépendance fournisseur et dérive des niveaux de service.",
        "recommendation_guidance": "Formaliser le pilotage (SLA/KPI), planifier des comités, documenter les revues et contractualiser les attentes de contrôle.",
    },
    "CO-04": {
        "process": "CO",
        "description": "Les journaux (logs) sont conservés selon une durée conforme aux exigences légales et aux politiques internes, permettant les investigations.",
        "test_procedure": "Vérifier les paramètres de rétention des logs et leur alignement avec la politique de conservation et les exigences réglementaires.",
        "risk_guidance": "Impossibilité de reconstituer des événements et difficulté à investiguer des incidents (conformité, sécurité).",
        "recommendation_guidance": "Aligner la rétention des logs (au moins 12 mois selon exigences) et mettre en place une surveillance/archivage centralisé si nécessaire.",
    },
    "CO-05": {
        "process": "CO",
        "description": "Le plan de continuité / reprise (PCA/PRA) est à jour, testé périodiquement et aligné avec les versions applicatives et l’infrastructure.",
        "test_procedure": "Revoir la documentation PRA, vérifier la date du dernier test, les résultats, et l’actualisation suite aux évolutions majeures.",
        "risk_guidance": "Indisponibilité prolongée et incapacité à respecter les objectifs RTO/RPO en cas de sinistre, avec impacts financiers et opérationnels.",
        "recommendation_guidance": "Planifier des tests PRA réguliers, actualiser la documentation après chaque évolution et formaliser un calendrier de tests validé par le métier.",
    },
    "CO-06": {
        "process": "CO",
        "description": "Les comptes de service et comptes techniques sont gérés de manière sécurisée (rotation des secrets, interdiction des mots de passe non expirables, coffre-fort).",
        "test_procedure": "Identifier les comptes de service, vérifier les politiques d’expiration/rotation et les contrôles de stockage des secrets.",
        "risk_guidance": "Compromission durable de comptes techniques à privilèges, permettant un accès persistant aux systèmes et données.",
        "recommendation_guidance": "Mettre en place une rotation périodique des mots de passe/secrets, supprimer l’option “non expirables” et déployer un coffre-fort (PAM) si possible.",
    },
    "CO-07": {
        "process": "CO",
        "description": "Les procédures de restauration sont documentées, validées et testées (scénarios de perte partielle et totale), avec preuves de tests.",
        "test_procedure": "Revoir la documentation de restauration et vérifier l’existence de tests récents (24 mois ou selon politique) et les résultats.",
        "risk_guidance": "Restauration inefficace en cas d’incident, entraînant perte de données et indisponibilité prolongée.",
        "recommendation_guidance": "Documenter une procédure de restauration complète, la valider, planifier des tests réguliers et traiter les écarts identifiés.",
    },
    "CO-08": {
        "process": "CO",
        "description": "Les correctifs de sécurité (patches) sont appliqués dans des délais conformes à la politique interne, avec priorisation selon criticité.",
        "test_procedure": "Comparer la criticité des patches éditeur avec les dates d’application et vérifier le respect des délais (ex: 30 jours pour critiques).",
        "risk_guidance": "Exposition à des vulnérabilités connues (SQL injection, escalade de privilèges) et compromission de l’application.",
        "recommendation_guidance": "Mettre en place une gestion des patches basée sur le risque, définir des fenêtres de maintenance et suivre les retards via des indicateurs.",
    },
    "CO-09": {
        "process": "CO",
        "description": "La capacité (stockage, CPU, mémoire) est pilotée via un plan formalisé, des seuils d’alerte et des projections de croissance.",
        "test_procedure": "Vérifier l’existence d’un capacity plan, les seuils, les alertes et les projections sur 12 mois, ainsi que le suivi des actions.",
        "risk_guidance": "Saturation des ressources entraînant dégradation de performance, indisponibilités et incidents lors des pics d’activité.",
        "recommendation_guidance": "Formaliser un plan de capacité, automatiser les alertes, définir des seuils et planifier les actions de dimensionnement.",
    },
}
