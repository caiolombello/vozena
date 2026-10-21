/* English is rendered in HTML; JavaScript adds an optional Portuguese experience. */
(() => {
  "use strict";

  const portuguese = {
    "skip": "Ir para o conteúdo",
    "home": "Início da Vozena",
    "navigation": "Navegação principal",
    "language": "Escolher idioma",
    "principles": "Princípios do produto",
    "nav.features": "Recursos",
    "nav.compatibility": "Compatibilidade",
    "nav.source": "Código ↗",
    "hero.eyebrow": "ÁUDIO NATIVO PARA LINUX · PRÉVIA v0.4.1",
    "hero.first": "Sua voz.",
    "hero.second": "Sem distrações.",
    "hero.description": "Um pouco mais de clareza para o seu Blue Yeti. Um app nativo para Linux que ajuda sua voz a chegar melhor nas chamadas, reuniões e em tudo o que você tem a dizer.",
    "hero.download": "Baixar Vozena para Linux",
    "hero.how": "Como funciona",
    "hero.note": "Grátis e de código aberto. Seu áudio fica no seu computador.",
    "hero.visual": "MENOS RUÍDO NO CAMINHO.",
    "hero.image": "Interface nativa da Vozena em português, mostrando controles de áudio do Blue Yeti, supressão de ruído, equalizador, volume e medidor pausado com valores de demonstração.",
    "hero.caption": "Interface nativa, com valores de demonstração.",
    "principle.native": "Nativo do seu desktop",
    "principle.local": "Processamento local",
    "principle.account": "Sem conta. Sem assinatura.",
    "principle.open": "Aberto desde o início",
    "signal.eyebrow": "MENOS AJUSTES. MAIS CONVERSA.",
    "signal.title": "Espaço para\no que importa.",
    "signal.description": "Preserve a identidade da sua voz. Reduza o ruído de fundo, ajuste o timbre e encontre um volume confortável antes da próxima chamada.",
    "signal.disclaimer": "Ilustração decorativa de sinal — não representa uma comparação medida de antes e depois.",
    "signal.noise.title": "Menos ruído de fundo",
    "signal.noise.body": "O RNNoise reduz o ruído de fundo localmente, ajudando a destacar sua fala.",
    "signal.eq.title": "Clareza do seu jeito",
    "signal.eq.body": "Ajuste o equalizador para dar forma à sua voz. Você mantém o controle do som que faz sentido para você.",
    "signal.level.title": "Um nível que você vê",
    "signal.level.body": "Ajuste o volume de saída e acompanhe o medidor real de nível para identificar picos antes da chamada.",
    "how.eyebrow": "CONECTOU. AJUSTOU. PODE FALAR.",
    "how.title": "Um ajuste simples.\nUma chamada tranquila.",
    "how.intro": "A Vozena cria um microfone com áudio processado para seu app de chamadas. Você escolhe o som; seu desktop cuida do restante.",
    "how.setup": "Ver os passos de instalação",
    "how.one.title": "Conecte seu Yeti",
    "how.one.body": "Abra a Vozena com seu Blue Yeti USB clássico conectado. O ganho e o padrão de captação continuam nos controles físicos do microfone.",
    "how.two.title": "Encontre seu som",
    "how.two.body": "Faça uma calibração guiada de 10 segundos. Revise as sugestões e aplique quando quiser. Se preferir, ouça uma amostra A/B.",
    "how.three.title": "Ative e selecione “Yeti Processado”",
    "how.three.body": "Clique em “Ativar tratamento” na Vozena e selecione “Yeti Processado” nas configurações de áudio do seu app de reuniões. Deixe a Vozena na bandeja e siga com a conversa.",
    "details.eyebrow": "CUIDADO EM CADA DETALHE",
    "details.title": "Controle,\nsem complicação.",
    "details.intro": "Ferramentas úteis para seu microfone, em um cantinho tranquilo do seu desktop.",
    "details.calibrate.title": "Uma ajuda para começar",
    "details.calibrate.body": "Uma calibração de 10 segundos sugere ajustes para sua voz e seu ambiente. As sugestões só entram em uso quando você decide aplicá-las.",
    "details.listen.title": "Ouça e compare",
    "details.listen.body": "Grave uma amostra de 10 segundos e compare o áudio original com o processado. A amostra fica apenas na memória, sem salvar uma gravação.",
    "details.mute.title": "Silêncio ao seu alcance",
    "details.mute.body": "Silencie pela bandeja ou use um atalho global no KDE. Continue na conversa sem precisar procurar a janela do app.",
    "details.reconnect.title": "Desconectou? Reconecte.",
    "details.reconnect.body": "A reconexão automática recupera seu microfone quando ele volta a ser conectado e simplifica o uso no dia a dia.",
    "compatibility.eyebrow": "FEITO PARA LINUX. CLARO SOBRE OS LIMITES.",
    "compatibility.title": "Um ponto de partida claro.",
    "compatibility.intro": "A Vozena é uma primeira prévia pública, criada e testada com um desktop e um microfone reais. Este é o cenário validado até aqui.",
    "compatibility.tested": "CONFIGURAÇÃO VALIDADA",
    "compatibility.hardware": "Blue Yeti USB clássico",
    "compatibility.languages": "Interface do app: português. Documentação: inglês e português.",
    "compatibility.limit": "Outras distribuições Linux, ambientes gráficos e microfones ainda não foram verificados. O atalho global funciona somente no KDE. Windows e macOS não são suportados.",
    "privacy.title": "Seu microfone.\nSeu computador.",
    "privacy.body": "O áudio é processado localmente. A Vozena não envia seu áudio para um serviço na nuvem.",
    "privacy.account": "Sem conta ou login",
    "privacy.telemetry": "Sem telemetria",
    "privacy.subscription": "Sem assinatura",
    "privacy.recording": "Amostras A/B apenas na memória",
    "privacy.footnote": "Seu app de reuniões continua seguindo as próprias configurações de áudio e privacidade.",
    "download.eyebrow": "SUA PRÓXIMA CHAMADA COMEÇA AQUI",
    "download.title": "Uma nova companhia\npara seu microfone.",
    "download.body": "Comece pela prévia v0.4.1. Você precisa de Fedora 44 ou Ubuntu 26.04 x86_64, Python 3.11 ou mais recente e do microfone testado. Siga as instruções de instalação a partir do código-fonte.",
    "download.button": "Baixar a versão mais recente",
    "download.note": "Linux · Código-fonte · GPL-3.0-or-later",
    "install.title": "PRIMEIROS PASSOS",
    "install.one.title": "Baixe e verifique",
    "install.one.body": "Baixe vozena-0.4.1-source.tar.gz e SHA256SUMS na página da versão. Verifique a soma de verificação do arquivo antes de extraí-lo.",
    "install.two.title": "Prepare seu desktop",
    "install.two.body": "Na pasta extraída, execute o comando abaixo. Ele instala as dependências de áudio verificadas e um ambiente Python próprio, sem abrir o app ou gravar áudio.",
    "install.three.title": "Abra a Vozena",
    "install.three.body": "Conecte seu Yeti e inicie o app. Clique em “Ativar tratamento” e selecione “Yeti Processado” no seu app de chamadas.",
    "install.guide": "Guia completo de instalação",
    "faq.eyebrow": "ALGUMAS BOAS PERGUNTAS",
    "faq.title": "Antes de\nconectar.",
    "faq.native.q": "É um app nativo ou uma ferramenta de navegador?",
    "faq.native.a": "A Vozena é um app nativo para desktop Linux. Ela usa o PipeWire para criar um microfone virtual com áudio processado chamado “Yeti Processado”, que você seleciona no app de chamadas. Este site nunca acessa seu microfone.",
    "faq.blue.q": "É um app oficial da Blue ou da Logitech?",
    "faq.blue.a": "Não. A Vozena é um projeto independente de código aberto, desenvolvido com um Blue Yeti USB clássico. Blue Yeti e Logitech são marcas de seus respectivos proprietários. O ganho e o padrão de captação continuam nos controles físicos do microfone.",
    "faq.audio.q": "Ela grava ou envia minhas conversas?",
    "faq.audio.a": "A Vozena processa o áudio do microfone localmente e não o envia para a nuvem. A ferramenta A/B opcional grava uma amostra de 10 segundos apenas na memória para você ouvir. Ela não é um gravador de conversas.",
    "faq.calls.q": "Vai funcionar com meu app de reuniões?",
    "faq.calls.a": "Ative “Ativar tratamento” na Vozena e selecione “Yeti Processado” em um app que aceite entradas de áudio do PipeWire. A configuração de desktop testada não garante suporte ao seu app de reuniões específico. Confira as entradas de áudio e faça uma chamada de teste.",
    "faq.echo.q": "Ela remove eco ou qualquer ruído de fundo?",
    "faq.echo.a": "A Vozena usa RNNoise para supressão de ruído. O resultado depende do ambiente, da posição do microfone e dos ajustes. Ela não oferece cancelamento de eco, e nenhum filtro pode prometer eliminar todos os sons.",
    "faq.preview.q": "O que significa “prévia”?",
    "faq.preview.a": "A v0.4.1 é uma versão pública de prévia, testada na configuração listada acima. É uma prévia para quem se sente à vontade para instalar um app Linux a partir do código-fonte e relatar problemas. A compatibilidade com outros cenários ainda precisa de testes.",
    "open.eyebrow": "UM APP PEQUENO. UM CONVITE ABERTO.",
    "open.title": "Melhor, em conjunto.",
    "open.body": "Conheça o código, conte o que encontrar ou ajude a testar outra configuração Linux. A Vozena tem código aberto e também tem espaço para a sua voz.",
    "open.button": "Conhecer no GitHub",
    "footer.tagline": "Um pouco de clareza. Um pouco de calma.",
    "footer.code": "Código-fonte",
    "footer.issues": "Relatar um problema",
    "footer.disclaimer": "Um projeto independente. Sem afiliação com a Blue ou a Logitech."
  };

  const textNodes = [...document.querySelectorAll("[data-i18n]")];
  const attributeNodes = [...document.querySelectorAll("[data-i18n-aria], [data-i18n-alt]")];
  const english = {};
  for (const element of textNodes) {
    english[element.dataset.i18n] = [...element.childNodes]
      .map(node => node.nodeName === "BR" ? "\n" : node.textContent).join("");
  }
  for (const element of attributeNodes) {
    if (element.dataset.i18nAria) english[element.dataset.i18nAria] = element.getAttribute("aria-label");
    if (element.dataset.i18nAlt) english[element.dataset.i18nAlt] = element.getAttribute("alt");
  }

  const meta = {
    en: {
      title: "Vozena — Your voice. Less noise.",
      description: "A native, open-source Linux app for clearer speech with your Blue Yeti. Local noise suppression, equalization, and guided calibration. No cloud audio.",
      social: "A calm, native Linux app for your Blue Yeti. Open source. Local audio. No subscription."
    },
    pt: {
      title: "Vozena — Sua voz. Sem distrações.",
      description: "Um app nativo e de código aberto para mais clareza com seu Blue Yeti no Linux. Supressão de ruído, equalização e calibração guiada. Sem áudio na nuvem.",
      social: "Um app nativo e tranquilo para seu Blue Yeti no Linux. Código aberto. Áudio local. Sem assinatura."
    }
  };

  function translate(language) {
    const strings = language === "pt" ? portuguese : english;
    document.documentElement.lang = language === "pt" ? "pt-BR" : "en";
    document.title = meta[language].title;
    document.querySelector('meta[name="description"]').content = meta[language].description;
    document.querySelector('meta[property="og:title"]').content = meta[language].title;
    document.querySelector('meta[property="og:description"]').content = meta[language].social;
    for (const element of textNodes) {
      const value = strings[element.dataset.i18n] ?? english[element.dataset.i18n];
      const fragment = document.createDocumentFragment();
      value.split("\n").forEach((line, index) => {
        if (index > 0) fragment.append(document.createElement("br"));
        fragment.append(document.createTextNode(line));
      });
      element.replaceChildren(fragment);
    }
    for (const element of attributeNodes) {
      for (const [key, attribute] of [["i18nAria", "aria-label"], ["i18nAlt", "alt"]]) {
        if (element.dataset[key]) element.setAttribute(attribute, strings[element.dataset[key]] ?? english[element.dataset[key]]);
      }
    }
    for (const link of document.querySelectorAll("[data-language]")) {
      if (link.dataset.language === language) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
  }

  function selectedLanguage() {
    const requested = new URL(window.location.href).searchParams.get("lang");
    if (requested === "en" || requested === "pt") return requested;
    try {
      if (window.localStorage.getItem("vozena-language") === "pt") return "pt";
    } catch { /* Language selection also works when storage is blocked. */ }
    return "en";
  }

  for (const link of document.querySelectorAll("[data-language]")) {
    link.addEventListener("click", event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const language = link.dataset.language;
      translate(language);
      const url = new URL(window.location.href);
      url.searchParams.set("lang", language);
      try { window.history.pushState({ language }, "", url); }
      catch { window.location.assign(url.href); }
      try { window.localStorage.setItem("vozena-language", language); }
      catch { /* Storage is optional; the URL keeps the selected language. */ }
    });
  }
  window.addEventListener("popstate", () => translate(selectedLanguage()));
  translate(selectedLanguage());
})();
