# Instructions pour toute session Claude sur ce projet

## Règle non négociable

Avant de modifier le moindre fichier : `git pull --rebase origin <branche>` (ou lancer `./start-work.sh`).
Avant de terminer la session : commit + `git push` (ou lancer `./end-work.sh`).

Ce projet est travaillé depuis plusieurs machines (Mac et mini-PC), parfois en parallèle. Ne jamais laisser du travail non poussé en fin de session — c'est la cause directe des divergences déjà rencontrées sur ce repo (voir le merge du 21/08/2026 avec le push venu du mini-PC en pleine session). Voir `SETUP.md` à la racine pour le détail du protocole.

## Travail inachevé

Si le changement en cours est un refactor ou une migration non finalisée, le mettre sur une branche `wip/...` séparée plutôt que sur la branche principale. Ne pas laisser la branche principale dans un état qui ne tourne pas.

## Avant de pousser

Vérifier que le fichier modifié compile / s'importe sans erreur avant de committer sur la branche principale.
