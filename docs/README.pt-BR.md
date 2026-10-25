<div align="center">

# Vozena

**Processamento de voz em tempo real para Linux.**  
Feito para voz limpa, dispositivos virtuais confiáveis e controle local claro.

[![CI](https://github.com/caiolombello/vozena/actions/workflows/ci.yml/badge.svg)](https://github.com/caiolombello/vozena/actions/workflows/ci.yml)
[![Licença: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](../LICENSE)

</div>

---

A Vozena v0.5.0 é uma versão pública de prévia. Ela foi validada em:

- Fedora 44 x86_64 com KDE Plasma, PipeWire 1.6 e o Blue Yeti USB clássico (`USB b58e:9e84`)
- Ubuntu e Kubuntu 26.04/26.10 x86_64: testes automatizados e verificações no PipeWire com um microfone virtual

Outras distribuições Linux, interfaces gráficas, arquiteturas e microfones ainda não foram validados. Windows e macOS não são compatíveis. O atalho global e o aviso na tela funcionam somente no KDE.

A Vozena não cancela eco e não promete remover todos os sons de fundo. Ela não controla o ganho físico nem o padrão de captação do microfone; faça esses ajustes no próprio Blue Yeti. Não há garantia de funcionamento com um aplicativo de chamadas específico.

## Instalar a versão de código-fonte v0.5.0

A versão publicada é um arquivo limpo de código-fonte. Ela não contém `.deps`, ambiente virtual, binários de plugins nem wheels do Python. Portanto, a preparação precisa de conexão de rede para baixar arquivos fixados do GitHub e do PyPI.

1. Instale os pré-requisitos do sistema:

   **No Fedora 44:**

   ```bash
   sudo dnf install python3 python3-pip pipewire pipewire-utils systemd \
     libsndfile libatomic libstdc++ xcb-util-cursor lsp-plugins-ladspa
   ```

   **No Ubuntu ou Kubuntu 26.04/26.10:**

   ```bash
   sudo apt install python3 python3-pip python3-venv pipewire pipewire-bin systemd \
     libsndfile1 libatomic1 libstdc++6 libxcb-cursor0 lsp-plugins-ladspa
   ```

   O `lsp-plugins-ladspa` fornece o compressor e o limitador. A Vozena só usa a cópia da sua distribuição depois de conferir que ela pertence ao sistema e tem todos os controles que a Vozena ajusta; assim, ela continua recebendo as atualizações da distribuição. Sem esse pacote, a preparação baixa uma versão fixada do Fedora 44, que exige glibc 2.43, além de `rpm` e `cpio` no Fedora ou `rpm2cpio` e `cpio` no Ubuntu.

2. Pelo navegador, baixe `vozena-0.5.0-source.tar.gz` e `SHA256SUMS` na [versão v0.5.0](https://github.com/caiolombello/vozena/releases/tag/v0.5.0). Coloque os dois arquivos na mesma pasta e confira o arquivo antes de extraí-lo:

   ```bash
   sha256sum --check SHA256SUMS
   tar -xzf vozena-0.5.0-source.tar.gz
   cd vozena-0.5.0
   ```

   Prossiga somente se o `sha256sum` mostrar `vozena-0.5.0-source.tar.gz: OK`.

3. Prepare e instale para o seu usuário:

   ```bash
   python3 scripts/prepare.py
   ```

   O script confere a plataforma, escolhe a origem do plugin LSP (`--lsp system` ou `--lsp pinned` força uma delas), baixa arquivos fixados por HTTPS, confere os hashes SHA-256, extrai apenas os plugins e as licenças necessários, instala os pacotes PySide6 fixados por hash em um ambiente isolado e persistente em `~/.local/share/vozena/runtime/` e instala o aplicativo. Ele nunca abre a Vozena nem capta áudio.

4. Abra a Vozena pelo menu de aplicativos ou execute:

   ```bash
   ~/.local/bin/vozena
   ```

   Para digitar apenas `vozena`, inclua `~/.local/bin` no seu `PATH`. O lançador antigo `~/.local/bin/yeti-voz` continua disponível por compatibilidade.

Para conferir uma preparação existente sem baixar, instalar, abrir o aplicativo ou captar áudio, execute:

```bash
python3 scripts/prepare.py --check
```

## Instalar a partir de um clone Git

Instale os pré-requisitos acima e o `git`, depois execute:

```bash
git clone https://github.com/caiolombello/vozena.git
cd vozena
python3 scripts/prepare.py
~/.local/bin/vozena
```

As opções de preparação para desenvolvimento e CI aparecem em `python3 scripts/prepare.py --help`. `--plugins-only` prepara apenas os plugins nativos, `--root` seleciona outro checkout do código e `--venv-dir` seleciona um diretório absoluto para o ambiente persistente.

## Usar

1. Conecte o Blue Yeti USB clássico e abra a Vozena. O aplicativo inicia pausado.
2. Ajuste **Redução de ruído**, **Clareza da voz** e **Volume da voz**, ou escolha um **Perfil de voz**. **Salvar** guarda os controles atuais como um perfil seu, por exemplo "Ventilador ligado"; **Excluir** remove o perfil.
3. Se quiser, abra **Calibrar** e faça a captura guiada de 10 segundos: fique em silêncio por 3 segundos, fale normalmente por 7 segundos, confira a sugestão e clique em **Aplicar ajustes**. A calibração nunca aplica uma sugestão sozinha.
4. Clique em **Ativar tratamento**.
5. Selecione **Yeti Processado** como microfone no aplicativo de chamadas. O cartão **Na sua reunião** mostra quais apps estão usando esse microfone. **Usar como microfone padrão** o torna a entrada padrão do sistema, para que os apps que seguem o padrão o usem automaticamente; **Restaurar microfone anterior** desfaz isso.
6. Com fones de ouvido, **Ouvir ao vivo** devolve a voz tratada em tempo real enquanto você ajusta os controles.
7. **Comparar áudio** grava uma amostra de 10 segundos e toca as versões original e tratada quando você pedir. Se a amostra sair em silêncio, confira o botão de mudo do Yeti (luz vermelha).

A aba **Preferências** pode iniciar o aplicativo instalado na bandeja ao entrar na sessão, ativar o tratamento ao abrir (esperando o Yeti se ele estiver desconectado) e avisar quando você falar com o Yeti Processado silenciado.

A Vozena reconecta o grafo PipeWire que ela própria criou depois que o Yeti, o PipeWire ou o computador volta. No KDE, `Meta+Shift+M` alterna o silêncio e o Plasma mostra o aviso de microfone na tela. Fechar a janela mantém o tratamento na bandeja do sistema quando há bandeja; use o menu da bandeja para encerrar.

### Quando o microfone capta áudio

Com o tratamento ativo, o Yeti não fica captando o tempo todo. Ele só funciona enquanto um app usa o Yeti Processado, enquanto a janela da Vozena está aberta (para o medidor de nível), durante o retorno ao vivo ou ao gravar uma amostra de comparação ou de calibração. O aviso de fala com microfone silenciado só escuta o Yeti enquanto um app de reunião já está usando o microfone, por meio de um fluxo passivo do PipeWire que não consegue abrir o microfone sozinho; nada é gravado.

Os ajustes de voz ficam em `~/.config/yeti-voice/settings.json`; as preferências e os seus perfis, em `~/.config/yeti-voice/preferences.json`. O pacote Python interno e os caminhos de dados locais mantêm os nomes `yeti_voice` e `yeti-voice` para preservar a compatibilidade com instalações existentes.

## Como funciona

A Vozena roda a própria cadeia de filtros do PipeWire entre o Yeti e um microfone virtual chamado **Yeti Processado**: filtro passa-altas de 80 Hz, redução de ruído RNNoise (misturada ao sinal original), equalização suave da voz, compressor LSP, ganho por software e limitador de picos LSP. Todos os plugins rodam localmente dentro do PipeWire; nenhum áudio é enviado pela rede.

## Desinstalar

Feche a Vozena, confira os caminhos pertencentes ao aplicativo que seriam removidos e só então desinstale:

```bash
python3 scripts/uninstall.py --dry-run
python3 scripts/uninstall.py
```

O desinstalador confere os marcadores de propriedade da Vozena e se recusa a continuar enquanto houver uma instância aberta. Ele remove as versões gerenciadas do aplicativo, o atalho do menu, a entrada de início automático e os lançadores principal e de compatibilidade. Os ajustes e as preferências em `~/.config/yeti-voice/` e o ambiente reutilizável em `~/.local/share/vozena/runtime/` são preservados.

## Contribuição e segurança

Consulte [CONTRIBUTING.md](../CONTRIBUTING.md) para os testes locais e os limites do projeto. Relate problemas de segurança pelo [formulário privado do GitHub](https://github.com/caiolombello/vozena/security/advisories/new), não por uma issue pública.

A Vozena é licenciada sob [GPL-3.0-or-later](../LICENSE). As dependências baixadas mantêm suas próprias licenças; consulte [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

A Vozena é um projeto independente de código aberto, sem afiliação ou endosso da Blue ou da Logitech. Blue Yeti e Logitech são marcas de seus respectivos proprietários.
