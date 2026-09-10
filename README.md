# Trading Platform

Plataforma de trading em desenvolvimento.

## Trabalhar noutra máquina

```sh
git clone <URL_DO_REPOSITORIO>
cd "Trading Platform"
```

Antes de começar a trabalhar, sincroniza a branch principal:

```sh
git switch main
git pull --ff-only
```

Cria uma branch para cada alteração e publica-a no GitHub:

```sh
git switch -c nome-da-alteracao
git push -u origin nome-da-alteracao
```

Nunca publiques credenciais. Usa ficheiros `.env` locais e mantém apenas um
`.env.example`, sem valores secretos, no repositório.
