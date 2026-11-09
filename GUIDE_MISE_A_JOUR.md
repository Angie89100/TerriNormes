# TerriNormes — Mise à jour du dépôt GitHub existant

Dépôt concerné : https://github.com/Angie89100/TerriNormes (branche `main`).

## 1. Avant d'importer

- Ne **supprimez** aucun fichier existant : `data/veille.json`, `veille/`, `.github/workflows/veille-juridique.yml` restent en place.
- Pour pouvoir revenir en arrière, conservez une copie du `index.html` actuel depuis GitHub (bouton **Download raw file**) ou l'historique des commits.
- Décompressez l'archive. Les chemins listés ci-dessous sont relatifs à la racine du dépôt, pas un dossier supplémentaire nommé « pret_pour_github ».

## 2. Fichier à remplacer

- `index.html` : remplacez celui de la racine par celui de l'archive. L'application affichera **277 références** (26 sources + 186 fiches + 65 fiches DAJ). Elle continue de charger le tableau de bord technique existant depuis `veille/veille-ui.js` et `data/veille.json`.

## 3. Fichiers à AJOUTER (ne remplacer aucun dossier existant)

- `daj_fiches.json` : catalogue initial des fiches DAJ et données d'actualisation.
- `veille.json` : stockage des publications du Journal officiel à collecter.
- `maj_fiches_daj.py` : collecteur des fiches DAJ.
- `maj_veille.py` : collecteur des publications DILA/JORF.
- `tests/test_maj_fiches_daj.py`, `tests/test_maj_veille.py` : tests du collecteur.
- `.github/workflows/actualiser-daj-jorf.yml` : **nouveau** workflow. Ne pas modifier l'ancien `veille-juridique.yml`.
- `GUIDE_MISE_A_JOUR.md` : ce mode d'emploi (facultatif sur GitHub).

## 4. Importer via GitHub

Dans le dépôt, onglet **Code**, branche `main`, choisir **Add file → Upload files**. Déposez le contenu décompressé à la racine en conservant les sous-dossiers `tests/` et `.github/workflows/`. Vérifiez les chemins et validez avec **Commit changes**. S'il est impossible d'importer les dossiers par glisser-déposer, utilisez **Add file → Create new file** avec le chemin exact, par exemple `.github/workflows/actualiser-daj-jorf.yml`.

## 5. Démarrer la nouvelle actualisation

1. Vérifiez que l'ancienne tâche GitHub Actions « TerriNormes - Veille documentaire » reste présente.
2. Ouvrez **Actions → TerriNormes - JORF et fiches DAJ → Run workflow** sur `main`.
3. Vérifiez les logs : tests, JORF, DAJ, commit, déploiement.
4. Vérifiez `veille.json` et `daj_fiches.json` pour les dates `last_success`. Si une collecte échoue, consultez les erreurs ; ne prétendez pas que les fiches sont à jour.
5. Ouvrez https://angie89100.github.io/TerriNormes/ avec Ctrl+F5, puis contrôlez **Fiches DAJ** (65 au départ), **Veille actualisée** et **Veille & sources** (les 5 sources précédentes).

## 6. Limites importantes

- La veille DAJ/JORF ne consolide pas le droit dans les 186 fiches pratiques.
- Le contrôle existant des 5 sources reste indépendant : 3 automatiques et 2 manuelles.
- Une réussite technique de GitHub Actions ne vaut pas vérification juridique.
- Les PDF DAJ sont seulement référencés ; le site officiel reste la source juridique à vérifier.
- Les programmations GitHub Actions peuvent subir des retards ou suspensions.
