# Instructions pour toute session Claude sur ce projet

## Règle non négociable

Avant de modifier le moindre fichier : `git pull --rebase origin <branche>` (ou lancer `./start-work.sh`).
Avant de terminer la session : commit + `git push` (ou lancer `./end-work.sh`).

Ce projet est travaillé depuis plusieurs machines (Mac et mini-PC), parfois en parallèle. Ne jamais laisser du travail non poussé en fin de session — c'est la cause directe des divergences déjà rencontrées sur ce repo (voir le merge du 21/08/2026 avec le push venu du mini-PC en pleine session). Voir `SETUP.md` à la racine pour le détail du protocole.

## Travail inachevé

Si le changement en cours est un refactor ou une migration non finalisée, le mettre sur une branche `wip/...` séparée plutôt que sur la branche principale. Ne pas laisser la branche principale dans un état qui ne tourne pas.

## Avant de pousser

Vérifier que le fichier modifié compile / s'importe sans erreur avant de committer sur la branche principale.

## Pièges de l'API IG

- Avant de changer d'epic ou d'instrument : passer un vrai ordre minimal (taille 1, SL et TP larges), puis le refermer aussitôt. `marketStatus: TRADEABLE` ne garantit pas le droit d'exécution : le 23/07, `CS.D.CFDGOLD.CFM.IP` rejetait tous les ordres en 403 (détail dans `app/assets_config.py`).
- Ne jamais supposer la forme des champs de `/history/transactions` : la vérifier sur une vraie réponse et sur les logs du bot. `transactionType` est traduit (`ORDRE` sur le compte démo FR, filtrer sur `cashTransaction`), chaque ligne est un trade complet (ouverture et clôture), et le signe de `size` suit le sens du trade d'origine (détail dans `app/brokers/ig_broker.py`).
