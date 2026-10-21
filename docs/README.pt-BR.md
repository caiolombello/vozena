<div align="center">

# Vozena

**Processamento de voz em tempo real para Linux.**  
Feito para voz limpa, dispositivos virtuais confiáveis e controle local claro.

[![CI](https://github.com/caiolombello/vozena/actions/workflows/ci.yml/badge.svg)](https://github.com/caiolombello/vozena/actions/workflows/ci.yml)
[![Licença: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](../LICENSE)

</div>

---

A Vozena v0.4.1 é uma versão pública de prévia. Ela foi validada em:

- Fedora 44 x86_64
- Ubuntu 26.04 x86_64
- KDE Plasma com PipeWire 1.6.9
- Blue Yeti USB clássico (`USB b58e:9e84`)

Outras distribuições Linux, interfaces gráficas, arquiteturas, versões do PipeWire e outros microfones ainda não foram validados. O pacote LSP fixado do Fedora exige glibc 2.43; por isso, o preparador aceita Fedora 44 e Ubuntu 26.04 x86_64. Windows e macOS não são compatíveis.

A Vozena não cancela eco e não promete remover todos os sons de fundo. Ela não controla o ganho físico nem o padrão de captação do microfone; faça esses ajustes no próprio Blue Yeti. Não há garantia de funcionamento com um aplicativo de chamadas específico.

## Instalar a versão de código-fonte v0.4.1

A versão publicada é um arquivo limpo de código-fonte. Ela não contém `.deps`, ambiente virtual, binários de plugins nem wheels do Python. Portanto, a preparação precisa de conexão de rede para baixar arquivos fixados do GitHub, Fedora e PyPI.

1. Instale os pré-requisitos do sistema:

   **No Fedora 44:**

   ```bash
   sudo dnf install python3 python3-pip pipewire pipewire-utils rpm cpio systemd \
     libsndfile libatomic libstdc++ xcb-util-cursor
   ```

   **No Ubuntu 26.04:**

   ```bash
   sudo apt install python3 python3-pip python3-venv pipewire pipewire-bin cpio systemd \
     libsndfile1 libatomic1 libstdc++6 libxcb-cursor0 rpm2cpio
   ```

   Uma instalação normal do Fedora 44 ou Ubuntu 26.04 KDE já fornece as demais bibliotecas gráficas do Qt usadas pelo aplicativo.

2. Pelo navegador, baixe `vozena-0.4.1-source.tar.gz` e `SHA256SUMS` na [versão v0.4.1](https://github.com/caiolombello/vozena/releases/tag/v0.4.1). Coloque os dois arquivos na mesma pasta e confira o arquivo antes de extraí-lo:

   ```bash
   sha256sum --check SHA256SUMS
   tar -xzf vozena-0.4.1-source.tar.gz
   cd vozena-0.4.1
   ```

   Prossiga somente se o `sha256sum` mostrar `vozena-0.4.1-source.tar.gz: OK`.

3. Prepare e instale para o seu usuário:

   ```bash
   python3 scripts/prepare.py
   ```

   O script confere a plataforma compatível, baixa arquivos fixados dos projetos de origem por HTTPS, verifica hashes SHA-256, extrai apenas os plugins e arquivos de licença necessários, instala os pacotes PySide6 fixados por hash em um ambiente persistente e isolado sob `~/.local/share/vozena/runtime/` e instala o aplicativo. Ele nunca abre a Vozena nem captura áudio.

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

Instale os pré-requisitos do sistema para a sua distribuição (Fedora ou Ubuntu) como indicado acima e execute:

```bash
git clone https://github.com/caiolombello/vozena.git
cd vozena
python3 scripts/prepare.py
~/.local/bin/vozena
```

Opções de preparação para desenvolvimento e integração contínua estão documentadas em `python3 scripts/prepare.py --help`. `--plugins-only` prepara apenas os plugins nativos fixados, `--root` seleciona outra pasta de código-fonte e `--venv-dir` define uma pasta persistente e absoluta para o ambiente de execução.

## Primeira configuração

1. Conecte seu Blue Yeti e mude a chave física de padrão polar na parte traseira para **Cardioide** (ícone em formato de coração).
2. Ajuste o botão físico de ganho na parte traseira para que sua fala mais alta nunca distorça.
3. Abra a Vozena e clique em **Ativar tratamento**.
4. No seu aplicativo de chamadas (Discord, Google Meet, Teams, Zoom, Slack, Telegram, OBS Studio), selecione **Yeti Processado** como microfone.
5. Nesse mesmo aplicativo, desative a supressão de ruído interna e o ganho automático para que dois filtros não disputem o mesmo sinal.

## Uso no dia a dia

- **Ícone na bandeja**: fechar a janela principal mantém a Vozena rodando na bandeja do sistema. Use o ícone para reabrir os controles ou fechar o aplicativo.
- **Atalho global para silenciar**: pressione <kbd>Meta</kbd>+<kbd>Shift</kbd>+<kbd>M</kbd> em qualquer lugar do desktop para alternar o silêncio. Você pode redefinir o atalho em **Configurações do KDE → Atalhos → Vozena**.
- **Controles rápidos**:
  - **Suavização de ruído**: ajuste o equilíbrio entre o som ambiente natural e uma supressão mais firme.
  - **Portão de ruído**: define o volume mínimo para fechar a captação de sons de fundo.
  - **Volume de saída**: ajuste fino do volume da voz tratada.
  - **Testar voz**: grave uma frase de teste na memória, escute a versão original comparada à tratada e aplique os ajustes calibrados.
- **Desconexão do microfone**: se você desconectar o Blue Yeti, a Vozena pausa automaticamente e libera o dispositivo. Conecte de novo e clique em **Reconectar**.

## Desinstalação

Para remover o aplicativo, o lançador e o atalho no menu, sem tocar nas suas preferências:

```bash
python3 scripts/uninstall.py
```

As preferências continuam salvas em `~/.config/yeti-voice/settings.json` e o ambiente Python isolado continua em `~/.local/share/vozena/runtime/`.

## Arquitetura

```
┌────────────────────────────────────────────────────────────────────────┐
│ Blue Yeti (nó físico ALSA / PipeWire)                                  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ PipeWire Filter Chain: vozena-yeti-sink                                │
│   ├─ Supressão de ruído LADSPA (RNNoise v1.10)                         │
│   ├─ Portão LADSPA (LSP Plugins v1.2.29)                               │
│   └─ Limitador LADSPA (LSP Plugins v1.2.29)                            │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fonte Virtual: Yeti Processado                                         │
│   └─ selecionada pelos aplicativos de chamadas                         │
└────────────────────────────────────────────────────────────────────────┘
```

Todo o processamento acontece no seu computador, por meio de plugins LADSPA carregados no PipeWire. Nenhum áudio é transmitido pela rede.

## Contribuição

Consulte [CONTRIBUTING.md](../CONTRIBUTING.md) e [SECURITY.md](../SECURITY.md) antes de enviar alterações ou relatar falhas de segurança.
