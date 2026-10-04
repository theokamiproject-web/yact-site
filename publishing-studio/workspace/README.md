# workspace/ — real issues live here (git-ignored)

`npm run publication:new -- <id>` creates `workspace/issues/<id>/`. **Everything below `workspace/` except this README is ignored by git**,
so unpublished manuscripts, photos, captions, notes and reviews cannot be committed by accident (and therefore cannot be published
by GitHub Pages, which serves the repository root).

Back the workspace up elsewhere (a private repository, a drive); Git is not protecting it.
To keep an issue in a *private* Git repository, point `PS_ISSUES_DIR` at a directory outside this repository.
