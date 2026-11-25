(function () {
  "use strict";

  var EN = {
    heroEyebrow:"DEVELOPER PORTAL · PRODUCTION CONTRACTS", heroLead:"Ship your first", heroAccent:"proven memory.", heroBody:"Start with a free actor-bound key, make a signed request, then publish your own capability into the federated catalog.", heroStart:"Start the guided setup", heroCode:"Run the first call", heroPublish:"Publish a capability", signalCapabilities:"live Hub capabilities", signalProviders:"signed providers", signalLanguages:"guide languages", terminalAria:"Animated path of a signed memory request",
    onboardEyebrow:"FIRST TEN MINUTES", onboardTitle:"One clear path into the network.", onboardBody:"No blockchain transaction is needed for the trial. Your private actor key stays in your runtime.", step1Tag:"CHOOSE", step1Title:"Pick the product surface", step1Body:"Personal, Team or Expert Market. Every access key is product-scoped.", step1Link:"Open setup wizard →", step2Tag:"IDENTITY", step2Title:"Create an Ed25519 actor", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"See the request →", step3Tag:"INVOKE", step3Title:"Write or discover", step3Body:"Call the product API; Gateway checks scope and Hub preserves trust state.", step3Link:"Browse contracts →", step4Tag:"VERIFY", step4Title:"Keep the receipt", step4Body:"Persist the memory ID, truth state and provenance receipt beside the output.", step4Link:"Open Attested Prove →",
    codeEyebrow:"COPY · SIGN · SEND", codeTitle:"A complete first write.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"The private key never becomes a header.", privateBody:"Only the public key and signature leave your process.", contractsEyebrow:"CONTRACT ATLAS", contractsTitle:"Every public surface, one click away.", contractsBody:"Use OpenAPI for direct product integration and the signed AI Market manifest for federated invocation.",
    publisherEyebrow:"CAPABILITY DISTRIBUTION", publisherTitle:"Yes — the Hub promotes its capabilities.", publisherBody:"Promotion is automatic after authorization; trust is never self-approved.", publisherAria:"Capability publication sequence", publish1Title:"Provider registers", publish1Body:"A signed provider publishes its schema, price, invoke URL and public key.", publish2Title:"Hub indexes", publish2Body:"The catalog exposes discovery metadata and records capability consumption.", publish3Title:"Hub announces", publish3Body:"Federation bootstrap announces the signed Hub identity to configured roots.", publish4Title:"Peers approve", publish4Body:"External operators inspect and pin the identity before granting trust.", automaticLabel:"AUTOMATIC", automaticTitle:"Registration, signed discovery, metrics and federation announcements.", approvalLabel:"OPERATOR CONTROLLED", approvalTitle:"Publisher token issuance, external approval and promotional channels.",
    manifestEyebrow:"MANIFEST LAB", manifestTitle:"Shape a capability before you publish it.", manifestBody:"This local builder generates a starter AI Market v2 entry. It sends nothing and stores nothing.", manifestNote:"Add the provider public key and obtain a scoped publisher token before registration.", finalEyebrow:"BUILD WITH EVIDENCE", finalTitle:"From first request to federated distribution.", finalBody:"Use the trial for integration, OpenAPI for contracts and the signed manifest when your capability is ready for agents.", finalStart:"Start integration", finalKova:"Study the KOVA boundary", finalDiscovery:"Open live discovery", footer:"Attested Memory · developer field kit"
  };

  var COPY = {
    en: EN,
    ru: {
      heroEyebrow:"ПОРТАЛ РАЗРАБОТЧИКА · PRODUCTION-КОНТРАКТЫ", heroLead:"Отправьте в сеть первую", heroAccent:"доказуемую память.", heroBody:"Начните с бесплатного ключа, привязанного к actor, выполните подписанный запрос и опубликуйте собственную capability в федеративном каталоге.", heroStart:"Запустить мастер", heroCode:"Выполнить первый запрос", heroPublish:"Опубликовать capability", signalCapabilities:"рабочих capabilities Hub", signalProviders:"подписанных провайдера", signalLanguages:"языков руководства", terminalAria:"Анимированный путь подписанного запроса памяти",
      onboardEyebrow:"ПЕРВЫЕ ДЕСЯТЬ МИНУТ", onboardTitle:"Один понятный путь в сеть.", onboardBody:"Для trial не нужна blockchain-транзакция. Приватный ключ actor остаётся в вашем runtime.", step1Tag:"ВЫБОР", step1Title:"Выберите продуктовый контур", step1Body:"Personal, Team или Expert Market. Каждый ключ ограничен одним продуктом.", step1Link:"Открыть мастер настройки →", step2Tag:"IDENTITY", step2Title:"Создайте Ed25519 actor", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Посмотреть запрос →", step3Tag:"ВЫЗОВ", step3Title:"Запишите или найдите", step3Body:"Вызовите API продукта: Gateway проверит scope, а Hub сохранит состояние доверия.", step3Link:"Открыть контракты →", step4Tag:"ПРОВЕРКА", step4Title:"Сохраните receipt", step4Body:"Храните memory ID, truth state и provenance receipt рядом с результатом.", step4Link:"Открыть Attested Prove →",
      codeEyebrow:"СКОПИРОВАТЬ · ПОДПИСАТЬ · ОТПРАВИТЬ", codeTitle:"Полный первый запрос записи.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"Приватный ключ никогда не становится HTTP-заголовком.", privateBody:"Процесс покидают только public key и подпись.", contractsEyebrow:"АТЛАС КОНТРАКТОВ", contractsTitle:"Все публичные интерфейсы в один клик.", contractsBody:"Используйте OpenAPI для прямой интеграции и подписанный AI Market manifest для федеративных вызовов.",
      publisherEyebrow:"РАСПРОСТРАНЕНИЕ CAPABILITIES", publisherTitle:"Да — Hub продвигает свои capabilities.", publisherBody:"После авторизации продвижение автоматическое; доверие никогда не подтверждается самим участником.", publisherAria:"Последовательность публикации capability", publish1Title:"Провайдер регистрируется", publish1Body:"Подписанный провайдер публикует schema, цену, invoke URL и public key.", publish2Title:"Hub индексирует", publish2Body:"Каталог открывает discovery-метаданные и учитывает потребление capability.", publish3Title:"Hub объявляет себя", publish3Body:"Federation bootstrap отправляет подписанную identity Hub настроенным корням.", publish4Title:"Пиры подтверждают", publish4Body:"Внешние операторы проверяют и закрепляют identity перед выдачей доверия.", automaticLabel:"АВТОМАТИЧЕСКИ", automaticTitle:"Регистрация, подписанный discovery, метрики и federation announcements.", approvalLabel:"ПОД КОНТРОЛЕМ ОПЕРАТОРА", approvalTitle:"Выдача publisher token, внешнее одобрение и маркетинговые каналы.",
      manifestEyebrow:"ЛАБОРАТОРИЯ МАНИФЕСТА", manifestTitle:"Соберите capability до публикации.", manifestBody:"Локальный конструктор создаёт начальную запись AI Market v2. Он ничего не отправляет и не сохраняет.", manifestNote:"Перед регистрацией добавьте public key провайдера и получите scoped publisher token.", finalEyebrow:"СТРОЙТЕ НА ДОКАЗАТЕЛЬСТВАХ", finalTitle:"От первого запроса до федеративного распространения.", finalBody:"Используйте trial для интеграции, OpenAPI для контрактов и подписанный manifest, когда capability готова для агентов.", finalStart:"Начать интеграцию", finalKova:"Изучить границу KOVA", finalDiscovery:"Открыть live discovery", footer:"Attested Memory · набор разработчика"
    },
    es: {
      heroEyebrow:"PORTAL DE DESARROLLO · CONTRATOS DE PRODUCCIÓN", heroLead:"Envía tu primera", heroAccent:"memoria demostrable.", heroBody:"Empieza con una clave gratuita ligada al actor, realiza una solicitud firmada y publica tu propia capability en el catálogo federado.", heroStart:"Iniciar configuración guiada", heroCode:"Ejecutar la primera llamada", heroPublish:"Publicar una capability", signalCapabilities:"capabilities activas del Hub", signalProviders:"proveedores firmados", signalLanguages:"idiomas de la guía", terminalAria:"Ruta animada de una solicitud de memoria firmada",
      onboardEyebrow:"PRIMEROS DIEZ MINUTOS", onboardTitle:"Un camino claro hacia la red.", onboardBody:"El trial no requiere transacción blockchain. La clave privada del actor permanece en tu runtime.", step1Tag:"ELEGIR", step1Title:"Elige la superficie de producto", step1Body:"Personal, Team o Expert Market. Cada clave se limita a un producto.", step1Link:"Abrir asistente →", step2Tag:"IDENTIDAD", step2Title:"Crea un actor Ed25519", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Ver la solicitud →", step3Tag:"INVOCAR", step3Title:"Escribe o descubre", step3Body:"Llama a la API; Gateway valida el alcance y Hub conserva el estado de confianza.", step3Link:"Ver contratos →", step4Tag:"VERIFICAR", step4Title:"Guarda el recibo", step4Body:"Conserva memory ID, truth state y provenance receipt junto al resultado.", step4Link:"Abrir Attested Prove →",
      codeEyebrow:"COPIAR · FIRMAR · ENVIAR", codeTitle:"Una primera escritura completa.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"La clave privada nunca se convierte en cabecera.", privateBody:"Solo salen del proceso la clave pública y la firma.", contractsEyebrow:"ATLAS DE CONTRATOS", contractsTitle:"Cada superficie pública, a un clic.", contractsBody:"Usa OpenAPI para integración directa y el manifiesto firmado de AI Market para invocación federada.",
      publisherEyebrow:"DISTRIBUCIÓN DE CAPABILITIES", publisherTitle:"Sí: el Hub promociona sus capabilities.", publisherBody:"La promoción es automática tras la autorización; la confianza nunca se autoaprueba.", publisherAria:"Secuencia de publicación de capabilities", publish1Title:"El proveedor se registra", publish1Body:"Publica esquema, precio, invoke URL y clave pública con firma.", publish2Title:"Hub indexa", publish2Body:"El catálogo expone discovery y registra el consumo.", publish3Title:"Hub se anuncia", publish3Body:"Federation bootstrap anuncia la identidad firmada a las raíces configuradas.", publish4Title:"Los peers aprueban", publish4Body:"Operadores externos revisan y fijan la identidad antes de confiar.", automaticLabel:"AUTOMÁTICO", automaticTitle:"Registro, discovery firmado, métricas y anuncios federados.", approvalLabel:"CONTROL DEL OPERADOR", approvalTitle:"Emisión de publisher token, aprobación externa y canales promocionales.",
      manifestEyebrow:"LABORATORIO DE MANIFIESTO", manifestTitle:"Da forma a una capability antes de publicarla.", manifestBody:"Este generador local crea una entrada inicial de AI Market v2. No envía ni guarda nada.", manifestNote:"Añade la clave pública y consigue un publisher token limitado antes de registrarte.", finalEyebrow:"CONSTRUYE CON EVIDENCIA", finalTitle:"De la primera solicitud a la distribución federada.", finalBody:"Usa el trial para integrar, OpenAPI para contratos y el manifiesto firmado cuando la capability esté lista.", finalStart:"Iniciar integración", finalKova:"Estudiar el límite KOVA", finalDiscovery:"Abrir discovery en vivo", footer:"Attested Memory · kit de desarrollo"
    },
    "pt-BR": {
      heroEyebrow:"PORTAL DO DESENVOLVEDOR · CONTRATOS DE PRODUÇÃO", heroLead:"Envie sua primeira", heroAccent:"memória comprovável.", heroBody:"Comece com uma chave gratuita ligada ao actor, faça uma solicitação assinada e publique sua capability no catálogo federado.", heroStart:"Iniciar configuração guiada", heroCode:"Executar primeira chamada", heroPublish:"Publicar capability", signalCapabilities:"capabilities ativas do Hub", signalProviders:"provedores assinados", signalLanguages:"idiomas do guia", terminalAria:"Caminho animado de uma solicitação de memória assinada",
      onboardEyebrow:"PRIMEIROS DEZ MINUTOS", onboardTitle:"Um caminho claro para a rede.", onboardBody:"O trial não exige transação blockchain. A chave privada do actor fica no runtime.", step1Tag:"ESCOLHER", step1Title:"Escolha o produto", step1Body:"Personal, Team ou Expert Market. Cada chave é limitada a um produto.", step1Link:"Abrir assistente →", step2Tag:"IDENTIDADE", step2Title:"Crie um actor Ed25519", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Ver solicitação →", step3Tag:"INVOCAR", step3Title:"Grave ou descubra", step3Body:"Chame a API; o Gateway valida o escopo e o Hub preserva o estado de confiança.", step3Link:"Ver contratos →", step4Tag:"VERIFICAR", step4Title:"Guarde o receipt", step4Body:"Mantenha memory ID, truth state e provenance receipt junto do resultado.", step4Link:"Abrir Attested Prove →",
      codeEyebrow:"COPIAR · ASSINAR · ENVIAR", codeTitle:"Uma primeira gravação completa.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"A chave privada nunca vira header.", privateBody:"Somente a chave pública e a assinatura saem do processo.", contractsEyebrow:"ATLAS DE CONTRATOS", contractsTitle:"Toda superfície pública a um clique.", contractsBody:"Use OpenAPI para integração direta e o manifesto assinado do AI Market para invocação federada.",
      publisherEyebrow:"DISTRIBUIÇÃO DE CAPABILITIES", publisherTitle:"Sim — o Hub promove suas capabilities.", publisherBody:"A promoção é automática após autorização; a confiança nunca é autoaprovada.", publisherAria:"Sequência de publicação de capability", publish1Title:"Provedor registra", publish1Body:"Publica schema, preço, invoke URL e chave pública assinados.", publish2Title:"Hub indexa", publish2Body:"O catálogo expõe discovery e registra consumo.", publish3Title:"Hub anuncia", publish3Body:"O bootstrap anuncia a identidade assinada às raízes configuradas.", publish4Title:"Peers aprovam", publish4Body:"Operadores externos verificam e fixam a identidade antes de confiar.", automaticLabel:"AUTOMÁTICO", automaticTitle:"Registro, discovery assinado, métricas e anúncios federados.", approvalLabel:"CONTROLADO PELO OPERADOR", approvalTitle:"Emissão de publisher token, aprovação externa e canais promocionais.",
      manifestEyebrow:"LABORATÓRIO DE MANIFESTO", manifestTitle:"Modele uma capability antes de publicar.", manifestBody:"Este gerador local cria uma entrada inicial AI Market v2. Não envia nem armazena nada.", manifestNote:"Adicione a chave pública e obtenha um publisher token limitado antes do registro.", finalEyebrow:"CONSTRUA COM EVIDÊNCIA", finalTitle:"Da primeira solicitação à distribuição federada.", finalBody:"Use trial para integração, OpenAPI para contratos e o manifesto assinado quando a capability estiver pronta.", finalStart:"Iniciar integração", finalKova:"Estudar limite KOVA", finalDiscovery:"Abrir discovery ao vivo", footer:"Attested Memory · kit do desenvolvedor"
    },
    de: {
      heroEyebrow:"ENTWICKLERPORTAL · PRODUKTIONSVERTRÄGE", heroLead:"Senden Sie Ihre erste", heroAccent:"belegbare Memory.", heroBody:"Starten Sie mit einem kostenlosen Actor-gebundenen Schlüssel, senden Sie eine signierte Anfrage und veröffentlichen Sie Ihre Capability im föderierten Katalog.", heroStart:"Geführtes Setup starten", heroCode:"Ersten Aufruf ausführen", heroPublish:"Capability veröffentlichen", signalCapabilities:"aktive Hub-Capabilities", signalProviders:"signierte Provider", signalLanguages:"Guide-Sprachen", terminalAria:"Animierter Pfad einer signierten Memory-Anfrage",
      onboardEyebrow:"DIE ERSTEN ZEHN MINUTEN", onboardTitle:"Ein klarer Weg ins Netzwerk.", onboardBody:"Für den Trial ist keine Blockchain-Transaktion nötig. Der private Actor-Schlüssel bleibt in Ihrer Runtime.", step1Tag:"WÄHLEN", step1Title:"Produktoberfläche wählen", step1Body:"Personal, Team oder Expert Market. Jeder Schlüssel gilt nur für ein Produkt.", step1Link:"Setup-Assistent öffnen →", step2Tag:"IDENTITÄT", step2Title:"Ed25519-Actor erstellen", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Anfrage ansehen →", step3Tag:"AUFRUF", step3Title:"Schreiben oder entdecken", step3Body:"Produkt-API aufrufen; Gateway prüft den Scope, Hub bewahrt den Vertrauensstatus.", step3Link:"Verträge öffnen →", step4Tag:"PRÜFEN", step4Title:"Receipt aufbewahren", step4Body:"Memory-ID, Truth State und Provenance Receipt mit dem Ergebnis speichern.", step4Link:"Attested Prove öffnen →",
      codeEyebrow:"KOPIEREN · SIGNIEREN · SENDEN", codeTitle:"Ein vollständiger erster Write.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"Der private Schlüssel wird nie zum Header.", privateBody:"Nur Public Key und Signatur verlassen den Prozess.", contractsEyebrow:"VERTRAGSATLAS", contractsTitle:"Jede öffentliche Oberfläche mit einem Klick.", contractsBody:"OpenAPI für direkte Integration, das signierte AI-Market-Manifest für föderierte Aufrufe.",
      publisherEyebrow:"CAPABILITY-VERTEILUNG", publisherTitle:"Ja — der Hub bewirbt seine Capabilities.", publisherBody:"Nach Autorisierung automatisch; Vertrauen wird nie selbst genehmigt.", publisherAria:"Ablauf der Capability-Veröffentlichung", publish1Title:"Provider registriert", publish1Body:"Er veröffentlicht Schema, Preis, Invoke-URL und Public Key.", publish2Title:"Hub indexiert", publish2Body:"Der Katalog zeigt Discovery-Daten und erfasst Verbrauch.", publish3Title:"Hub kündigt sich an", publish3Body:"Der Bootstrap meldet die signierte Hub-Identität an konfigurierte Roots.", publish4Title:"Peers genehmigen", publish4Body:"Externe Betreiber prüfen und pinnen die Identität.", automaticLabel:"AUTOMATISCH", automaticTitle:"Registrierung, signiertes Discovery, Metriken und Federation Announcements.", approvalLabel:"BETREIBERGESTEUERT", approvalTitle:"Publisher-Token, externe Freigabe und Werbekanäle.",
      manifestEyebrow:"MANIFEST-LABOR", manifestTitle:"Capability vor Veröffentlichung formen.", manifestBody:"Der lokale Generator erstellt einen AI-Market-v2-Entwurf. Er sendet und speichert nichts.", manifestNote:"Public Key ergänzen und vor Registrierung ein begrenztes Publisher-Token erhalten.", finalEyebrow:"MIT BELEGEN BAUEN", finalTitle:"Von der ersten Anfrage zur föderierten Verteilung.", finalBody:"Trial für Integration, OpenAPI für Verträge und das signierte Manifest für agentenreife Capabilities.", finalStart:"Integration starten", finalKova:"KOVA-Grenze verstehen", finalDiscovery:"Live-Discovery öffnen", footer:"Attested Memory · Entwickler-Kit"
    },
    fr: {
      heroEyebrow:"PORTAIL DÉVELOPPEUR · CONTRATS DE PRODUCTION", heroLead:"Envoyez votre première", heroAccent:"mémoire prouvable.", heroBody:"Commencez avec une clé gratuite liée à l’actor, effectuez une requête signée puis publiez votre capability dans le catalogue fédéré.", heroStart:"Lancer la configuration guidée", heroCode:"Exécuter le premier appel", heroPublish:"Publier une capability", signalCapabilities:"capabilities actives du Hub", signalProviders:"fournisseurs signés", signalLanguages:"langues du guide", terminalAria:"Parcours animé d’une requête mémoire signée",
      onboardEyebrow:"LES DIX PREMIÈRES MINUTES", onboardTitle:"Un chemin clair vers le réseau.", onboardBody:"Le trial ne nécessite aucune transaction blockchain. La clé privée de l’actor reste dans votre runtime.", step1Tag:"CHOISIR", step1Title:"Choisissez la surface produit", step1Body:"Personal, Team ou Expert Market. Chaque clé est limitée à un produit.", step1Link:"Ouvrir l’assistant →", step2Tag:"IDENTITÉ", step2Title:"Créez un actor Ed25519", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Voir la requête →", step3Tag:"INVOQUER", step3Title:"Écrivez ou découvrez", step3Body:"Appelez l’API ; Gateway vérifie le scope et Hub conserve l’état de confiance.", step3Link:"Voir les contrats →", step4Tag:"VÉRIFIER", step4Title:"Conservez le reçu", step4Body:"Gardez memory ID, truth state et provenance receipt avec le résultat.", step4Link:"Ouvrir Attested Prove →",
      codeEyebrow:"COPIER · SIGNER · ENVOYER", codeTitle:"Une première écriture complète.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"La clé privée ne devient jamais un header.", privateBody:"Seules la clé publique et la signature quittent le processus.", contractsEyebrow:"ATLAS DES CONTRATS", contractsTitle:"Chaque surface publique en un clic.", contractsBody:"Utilisez OpenAPI en direct et le manifeste AI Market signé pour les invocations fédérées.",
      publisherEyebrow:"DISTRIBUTION DES CAPABILITIES", publisherTitle:"Oui — le Hub promeut ses capabilities.", publisherBody:"Promotion automatique après autorisation ; la confiance ne s’autoapprouve jamais.", publisherAria:"Séquence de publication d’une capability", publish1Title:"Le fournisseur s’enregistre", publish1Body:"Il publie schema, prix, invoke URL et clé publique signés.", publish2Title:"Hub indexe", publish2Body:"Le catalogue expose le discovery et comptabilise la consommation.", publish3Title:"Hub s’annonce", publish3Body:"Le bootstrap annonce l’identité signée aux racines configurées.", publish4Title:"Les peers approuvent", publish4Body:"Les opérateurs externes inspectent et épinglent l’identité.", automaticLabel:"AUTOMATIQUE", automaticTitle:"Enregistrement, discovery signé, métriques et annonces fédérées.", approvalLabel:"CONTRÔLÉ PAR L’OPÉRATEUR", approvalTitle:"Publisher token, approbation externe et canaux promotionnels.",
      manifestEyebrow:"LABORATOIRE DU MANIFESTE", manifestTitle:"Façonnez une capability avant publication.", manifestBody:"Ce générateur local produit une entrée AI Market v2. Il n’envoie et ne stocke rien.", manifestNote:"Ajoutez la clé publique et obtenez un publisher token limité avant l’enregistrement.", finalEyebrow:"CONSTRUIRE AVEC DES PREUVES", finalTitle:"De la première requête à la distribution fédérée.", finalBody:"Trial pour intégrer, OpenAPI pour les contrats, manifeste signé pour les agents.", finalStart:"Démarrer l’intégration", finalKova:"Étudier la limite KOVA", finalDiscovery:"Ouvrir le discovery live", footer:"Attested Memory · kit développeur"
    },
    ja: {
      heroEyebrow:"開発者ポータル · PRODUCTION CONTRACT", heroLead:"最初の", heroAccent:"証明可能な memory を送信。", heroBody:"actor-bound の無料 key で開始し、署名 request を実行して、自分の capability を federated catalog に公開します。", heroStart:"ガイド付きセットアップ", heroCode:"最初の call を実行", heroPublish:"Capability を公開", signalCapabilities:"稼働中 Hub capabilities", signalProviders:"署名済み provider", signalLanguages:"ガイド言語", terminalAria:"署名済み memory request のアニメーション経路",
      onboardEyebrow:"最初の10分", onboardTitle:"Network への明確な一本道。", onboardBody:"Trial に blockchain transaction は不要です。actor private key は runtime 内に残ります。", step1Tag:"選択", step1Title:"Product surface を選ぶ", step1Body:"Personal、Team、Expert Market。各 access key は product-scoped です。", step1Link:"セットアップを開く →", step2Tag:"IDENTITY", step2Title:"Ed25519 actor を作成", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Request を見る →", step3Tag:"INVOKE", step3Title:"書き込みまたは検索", step3Body:"Product API を呼び出すと Gateway が scope を確認し Hub が trust state を保持します。", step3Link:"Contract を見る →", step4Tag:"VERIFY", step4Title:"Receipt を保存", step4Body:"Memory ID、truth state、provenance receipt を output と一緒に保存します。", step4Link:"Attested Prove を開く →",
      codeEyebrow:"COPY · SIGN · SEND", codeTitle:"完全な最初の write。", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"Private key は header になりません。", privateBody:"Process 外へ出るのは public key と signature だけです。", contractsEyebrow:"CONTRACT ATLAS", contractsTitle:"すべての public surface にワンクリック。", contractsBody:"直接連携には OpenAPI、federated invoke には署名済み AI Market manifest を使用します。",
      publisherEyebrow:"CAPABILITY DISTRIBUTION", publisherTitle:"はい — Hub は capability を自動配信します。", publisherBody:"認可後の promotion は自動ですが、trust は自己承認できません。", publisherAria:"Capability 公開シーケンス", publish1Title:"Provider が登録", publish1Body:"署名済み schema、価格、invoke URL、public key を公開します。", publish2Title:"Hub が index", publish2Body:"Catalog が discovery metadata を公開し consumption を記録します。", publish3Title:"Hub が announce", publish3Body:"Bootstrap が署名済み Hub identity を設定済み root に通知します。", publish4Title:"Peer が承認", publish4Body:"外部 operator が identity を確認・pin して trust を与えます。", automaticLabel:"自動", automaticTitle:"登録、署名 discovery、metrics、federation announcement。", approvalLabel:"OPERATOR 管理", approvalTitle:"Publisher token 発行、外部承認、promotion channel。",
      manifestEyebrow:"MANIFEST LAB", manifestTitle:"公開前に capability を設計。", manifestBody:"ローカル builder が AI Market v2 の starter entry を生成します。送信も保存もしません。", manifestNote:"登録前に provider public key と scoped publisher token を用意してください。", finalEyebrow:"EVIDENCE で構築", finalTitle:"最初の request から federated distribution まで。", finalBody:"Trial で統合し、OpenAPI で contract を確認し、agent-ready になったら署名 manifest を使います。", finalStart:"統合を開始", finalKova:"KOVA boundary を学ぶ", finalDiscovery:"Live discovery を開く", footer:"Attested Memory · developer field kit"
    },
    ko: {
      heroEyebrow:"개발자 포털 · PRODUCTION CONTRACT", heroLead:"첫 번째", heroAccent:"증명 가능한 memory를 전송하세요.", heroBody:"actor-bound 무료 key로 시작해 서명 request를 실행하고 capability를 federated catalog에 게시하세요.", heroStart:"가이드 설정 시작", heroCode:"첫 call 실행", heroPublish:"Capability 게시", signalCapabilities:"활성 Hub capabilities", signalProviders:"서명된 provider", signalLanguages:"가이드 언어", terminalAria:"서명된 memory request의 애니메이션 경로",
      onboardEyebrow:"첫 10분", onboardTitle:"Network로 가는 명확한 한 경로.", onboardBody:"Trial에는 blockchain transaction이 필요 없습니다. actor private key는 runtime에 남습니다.", step1Tag:"선택", step1Title:"Product surface 선택", step1Body:"Personal, Team 또는 Expert Market. 각 key는 하나의 product scope만 가집니다.", step1Link:"설정 마법사 열기 →", step2Tag:"IDENTITY", step2Title:"Ed25519 actor 생성", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Request 보기 →", step3Tag:"INVOKE", step3Title:"기록 또는 검색", step3Body:"Product API를 호출하면 Gateway가 scope를 확인하고 Hub가 trust state를 보존합니다.", step3Link:"Contract 보기 →", step4Tag:"VERIFY", step4Title:"Receipt 보관", step4Body:"Memory ID, truth state, provenance receipt를 output과 함께 저장합니다.", step4Link:"Attested Prove 열기 →",
      codeEyebrow:"COPY · SIGN · SEND", codeTitle:"완전한 첫 write.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"Private key는 header가 되지 않습니다.", privateBody:"Public key와 signature만 process 밖으로 나갑니다.", contractsEyebrow:"CONTRACT ATLAS", contractsTitle:"모든 public surface를 한 번에.", contractsBody:"직접 연동에는 OpenAPI, federated invoke에는 서명된 AI Market manifest를 사용하세요.",
      publisherEyebrow:"CAPABILITY DISTRIBUTION", publisherTitle:"예 — Hub가 capabilities를 홍보합니다.", publisherBody:"인증 후 promotion은 자동이지만 trust는 스스로 승인할 수 없습니다.", publisherAria:"Capability 게시 순서", publish1Title:"Provider 등록", publish1Body:"서명된 schema, 가격, invoke URL, public key를 게시합니다.", publish2Title:"Hub index", publish2Body:"Catalog가 discovery metadata를 공개하고 consumption을 기록합니다.", publish3Title:"Hub announce", publish3Body:"Bootstrap이 서명된 Hub identity를 설정된 root에 알립니다.", publish4Title:"Peer 승인", publish4Body:"외부 operator가 identity를 검토하고 pin한 뒤 trust를 부여합니다.", automaticLabel:"자동", automaticTitle:"등록, 서명 discovery, metrics, federation announcement.", approvalLabel:"OPERATOR 제어", approvalTitle:"Publisher token 발급, 외부 승인, promotion channel.",
      manifestEyebrow:"MANIFEST LAB", manifestTitle:"게시 전에 capability를 설계하세요.", manifestBody:"로컬 builder가 AI Market v2 starter entry를 생성합니다. 전송하거나 저장하지 않습니다.", manifestNote:"등록 전 provider public key와 scoped publisher token을 준비하세요.", finalEyebrow:"EVIDENCE로 구축", finalTitle:"첫 request부터 federated distribution까지.", finalBody:"Trial로 연동하고 OpenAPI로 contract를 확인한 뒤 agent-ready capability에 서명 manifest를 사용하세요.", finalStart:"연동 시작", finalKova:"KOVA boundary 보기", finalDiscovery:"Live discovery 열기", footer:"Attested Memory · developer field kit"
    },
    "zh-CN": {
      heroEyebrow:"开发者门户 · PRODUCTION CONTRACT", heroLead:"发送你的第一个", heroAccent:"可证明 memory。", heroBody:"从 actor-bound 免费 key 开始，完成签名 request，然后将 capability 发布到 federated catalog。", heroStart:"启动引导设置", heroCode:"执行首次 call", heroPublish:"发布 capability", signalCapabilities:"运行中的 Hub capabilities", signalProviders:"签名 provider", signalLanguages:"指南语言", terminalAria:"签名 memory request 的动画路径",
      onboardEyebrow:"最初十分钟", onboardTitle:"进入 network 的清晰路径。", onboardBody:"Trial 无需 blockchain transaction。actor private key 始终留在 runtime 中。", step1Tag:"选择", step1Title:"选择 product surface", step1Body:"Personal、Team 或 Expert Market。每个 key 仅限一个 product scope。", step1Link:"打开设置向导 →", step2Tag:"IDENTITY", step2Title:"创建 Ed25519 actor", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"查看 request →", step3Tag:"INVOKE", step3Title:"写入或发现", step3Body:"调用 Product API；Gateway 检查 scope，Hub 保留 trust state。", step3Link:"查看 contract →", step4Tag:"VERIFY", step4Title:"保存 receipt", step4Body:"将 Memory ID、truth state 和 provenance receipt 与 output 一起保存。", step4Link:"打开 Attested Prove →",
      codeEyebrow:"COPY · SIGN · SEND", codeTitle:"完整的首次 write。", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"Private key 永远不会成为 header。", privateBody:"只有 public key 和 signature 会离开 process。", contractsEyebrow:"CONTRACT ATLAS", contractsTitle:"一键访问所有 public surface。", contractsBody:"直接集成使用 OpenAPI，federated invoke 使用签名 AI Market manifest。",
      publisherEyebrow:"CAPABILITY DISTRIBUTION", publisherTitle:"是的——Hub 会推广自己的 capabilities。", publisherBody:"授权后的 promotion 自动完成，但 trust 绝不能自我批准。", publisherAria:"Capability 发布顺序", publish1Title:"Provider 注册", publish1Body:"发布签名 schema、价格、invoke URL 和 public key。", publish2Title:"Hub 建立索引", publish2Body:"Catalog 暴露 discovery metadata 并记录 consumption。", publish3Title:"Hub 发出公告", publish3Body:"Bootstrap 将签名 Hub identity 通知已配置 root。", publish4Title:"Peer 批准", publish4Body:"外部 operator 检查并 pin identity 后才授予 trust。", automaticLabel:"自动", automaticTitle:"注册、签名 discovery、metrics 与 federation announcement。", approvalLabel:"OPERATOR 控制", approvalTitle:"Publisher token 发放、外部批准与 promotion channel。",
      manifestEyebrow:"MANIFEST LAB", manifestTitle:"发布前塑造 capability。", manifestBody:"本地 builder 生成 AI Market v2 starter entry，不发送也不存储任何内容。", manifestNote:"注册前请添加 provider public key 并取得 scoped publisher token。", finalEyebrow:"基于 EVIDENCE 构建", finalTitle:"从首次 request 到 federated distribution。", finalBody:"用 Trial 验证集成，用 OpenAPI 确认 contract，capability 面向 agent 后使用签名 manifest。", finalStart:"开始集成", finalKova:"了解 KOVA boundary", finalDiscovery:"打开 live discovery", footer:"Attested Memory · developer field kit"
    },
    tr: {
      heroEyebrow:"GELİŞTİRİCİ PORTALI · PRODUCTION CONTRACT", heroLead:"İlk", heroAccent:"kanıtlanabilir memory’nizi gönderin.", heroBody:"Actor-bound ücretsiz key ile başlayın, imzalı request yapın ve capability’nizi federated catalog’a yayınlayın.", heroStart:"Rehberli kurulumu başlat", heroCode:"İlk çağrıyı çalıştır", heroPublish:"Capability yayınla", signalCapabilities:"aktif Hub capabilities", signalProviders:"imzalı provider", signalLanguages:"rehber dili", terminalAria:"İmzalı memory request için animasyonlu yol",
      onboardEyebrow:"İLK ON DAKİKA", onboardTitle:"Network’e giden net bir yol.", onboardBody:"Trial için blockchain transaction gerekmez. Actor private key runtime içinde kalır.", step1Tag:"SEÇ", step1Title:"Product surface seçin", step1Body:"Personal, Team veya Expert Market. Her key tek bir product scope taşır.", step1Link:"Kurulum sihirbazını aç →", step2Tag:"IDENTITY", step2Title:"Ed25519 actor oluşturun", step2Body:"Keep the Ed25519 identity locally and sign each destination-bound request with actor proof v2.", step2Link:"Request’i gör →", step3Tag:"INVOKE", step3Title:"Yazın veya keşfedin", step3Body:"Product API çağrılır; Gateway scope’u denetler, Hub trust state’i korur.", step3Link:"Contract’ları aç →", step4Tag:"VERIFY", step4Title:"Receipt’i saklayın", step4Body:"Memory ID, truth state ve provenance receipt’i output ile birlikte saklayın.", step4Link:"Attested Prove’u aç →",
      codeEyebrow:"COPY · SIGN · SEND", codeTitle:"Eksiksiz ilk write.", codeBody:"Use the updated CLI or Python client. It signs the destination, method, path, query and exact body; legacy identity-only proofs are refused.", privateTitle:"Private key hiçbir zaman header olmaz.", privateBody:"Yalnızca public key ve signature process dışına çıkar.", contractsEyebrow:"CONTRACT ATLAS", contractsTitle:"Tüm public surface’ler tek tık uzakta.", contractsBody:"Doğrudan entegrasyon için OpenAPI, federated invoke için imzalı AI Market manifest kullanın.",
      publisherEyebrow:"CAPABILITY DISTRIBUTION", publisherTitle:"Evet — Hub capabilities’i tanıtır.", publisherBody:"Yetkilendirmeden sonra promotion otomatiktir; trust asla kendi kendine onaylanmaz.", publisherAria:"Capability yayınlama sırası", publish1Title:"Provider kayıt olur", publish1Body:"İmzalı schema, fiyat, invoke URL ve public key yayınlar.", publish2Title:"Hub indexler", publish2Body:"Catalog discovery metadata’yı sunar ve consumption’ı kaydeder.", publish3Title:"Hub duyurur", publish3Body:"Bootstrap imzalı Hub identity’yi ayarlı root’lara duyurur.", publish4Title:"Peer’ler onaylar", publish4Body:"Harici operator identity’yi inceler ve pin ederek trust verir.", automaticLabel:"OTOMATİK", automaticTitle:"Kayıt, imzalı discovery, metrics ve federation announcement.", approvalLabel:"OPERATOR KONTROLLÜ", approvalTitle:"Publisher token verilmesi, harici onay ve promotion kanalları.",
      manifestEyebrow:"MANIFEST LAB", manifestTitle:"Yayınlamadan önce capability’yi şekillendirin.", manifestBody:"Yerel builder bir AI Market v2 starter entry üretir; hiçbir şey göndermez veya saklamaz.", manifestNote:"Kayıttan önce provider public key ekleyin ve scoped publisher token alın.", finalEyebrow:"EVIDENCE İLE GELİŞTİR", finalTitle:"İlk request’ten federated distribution’a.", finalBody:"Entegrasyon için Trial, contract için OpenAPI ve agent-ready capability için imzalı manifest kullanın.", finalStart:"Entegrasyonu başlat", finalKova:"KOVA sınırını incele", finalDiscovery:"Live discovery aç", footer:"Attested Memory · geliştirici kiti"
    }
  };

  var HUB_SIGNAL_COPY = {
    en:["network capabilities", "indexed Hubs"],
    ru:["capabilities в сети", "индексированных Hub"],
    es:["capabilities en la red", "Hubs indexados"],
    "pt-BR":["capabilities na rede", "Hubs indexados"],
    de:["Capabilities im Netzwerk", "indexierte Hubs"],
    fr:["capabilities du réseau", "Hubs indexés"],
    ja:["ネットワーク capabilities", "index 済み Hub"],
    ko:["네트워크 capabilities", "index된 Hub"],
    "zh-CN":["网络 capabilities", "已索引 Hub"],
    tr:["network capabilities", "indexlenmiş Hub"]
  };

  function locale() {
    return window.AttestedLocale ? window.AttestedLocale.current() : "en";
  }

  function translate(lang) {
    var dictionary = COPY[lang] || EN;
    document.querySelectorAll("[data-dev-i18n]").forEach(function (node) {
      var key = node.dataset.devI18n;
      node.textContent = dictionary[key] || EN[key] || key;
    });
    document.querySelectorAll("[data-dev-i18n-aria]").forEach(function (node) {
      var key = node.dataset.devI18nAria;
      node.setAttribute("aria-label", dictionary[key] || EN[key] || key);
    });
  }

  function enableCodeTabs() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".dev-code-tab"));
    var panels = Array.prototype.slice.call(document.querySelectorAll(".dev-code-panel"));
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (item) {
          var active = item === tab;
          item.classList.toggle("active", active);
          item.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (panel) {
          var active = panel.dataset.codePanel === tab.dataset.codeTarget;
          panel.hidden = !active;
          panel.classList.toggle("active", active);
        });
      });
    });
  }

  function enableManifestLab() {
    var output = document.querySelector("#manifest-json");
    var fields = ["manifest-product", "manifest-capability", "manifest-url", "manifest-price"].map(function (id) { return document.getElementById(id); });
    if (!output || fields.some(function (field) { return !field; })) return;

    function safeId(value, fallback) {
      var clean = String(value || "").trim().replace(/[^a-zA-Z0-9@._-]/g, "-").replace(/-+/g, "-").slice(0, 100);
      return clean || fallback;
    }

    function render() {
      var product = safeId(fields[0].value, "my-product");
      var capability = safeId(fields[1].value, "task.run@v1");
      var invokeUrl = String(fields[2].value || "").trim();
      if (!/^https:\/\//i.test(invokeUrl)) invokeUrl = "https://provider.example/capabilities/" + product + "/" + capability + "/invoke";
      var price = Number(fields[3].value);
      if (!Number.isFinite(price) || price < 0) price = 0;
      output.textContent = JSON.stringify({
        product_id: product,
        capability_id: capability,
        name: capability.split("@")[0].replace(/[._-]+/g, " "),
        version: "v1",
        description: "Describe the request-bound result.",
        invoke_url: invokeUrl,
        price_per_call_usd: Number(price.toFixed(6)),
        publisher_id: "your-provider",
        provider_pubkey: "base64url-ed25519-public-key",
        input_schema: { type: "object", additionalProperties: true },
        output_schema: { type: "object", additionalProperties: true },
        category: "custom/agent-tool"
      }, null, 2);
    }

    fields.forEach(function (field) { field.addEventListener("input", render); });
    render();
  }

  function enablePublisherSequence() {
    var rail = document.querySelector(".publisher-rail");
    if (!rail || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
    var cards = Array.prototype.slice.call(rail.querySelectorAll("article"));
    var index = 0;
    var timer = 0;
    function tick() {
      cards.forEach(function (card, cardIndex) { card.classList.toggle("is-active", cardIndex === index); });
      rail.style.setProperty("--publisher-progress", (((index + 0.5) / cards.length) * 100).toFixed(2) + "%");
      index = (index + 1) % cards.length;
    }
    function start() { if (!timer) { tick(); timer = window.setInterval(tick, 1450); } }
    function stop() { window.clearInterval(timer); timer = 0; }
    if (!("IntersectionObserver" in window)) { start(); return; }
    new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { if (entry.isIntersecting) start(); else stop(); });
    }, { threshold: 0.18 }).observe(rail);
  }

  function paintHubSignalLabels(lang) {
    var labels = document.querySelectorAll(".dev-signals span");
    var copy = HUB_SIGNAL_COPY[lang] || HUB_SIGNAL_COPY.en;
    if (labels[0]) labels[0].textContent = copy[0];
    if (labels[1]) labels[1].textContent = copy[1];
  }

  function refreshHubSignals() {
    var totalNodes = document.querySelectorAll("[data-hub-total]");
    var indexedNodes = document.querySelectorAll("[data-hub-indexed]");
    if (!totalNodes.length && !indexedNodes.length) return;
    paintHubSignalLabels(locale());
    window.fetch("/hub-public/manifest", { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("manifest unavailable");
        return response.json();
      })
      .then(function (manifest) {
        var total = Number(manifest.total_capabilities);
        var indexed = Number(manifest.hubs_indexed);
        if (!Number.isFinite(total) || total < 0 || !Number.isFinite(indexed) || indexed < 0) throw new Error("invalid manifest counters");
        totalNodes.forEach(function (node) { node.textContent = String(total); });
        indexedNodes.forEach(function (node) { node.textContent = String(indexed); });
        document.documentElement.dataset.hubManifest = "live";
      })
      .catch(function () {
        document.documentElement.dataset.hubManifest = "unavailable";
      });
  }

  translate(locale());
  enableCodeTabs();
  enableManifestLab();
  enablePublisherSequence();
  refreshHubSignals();
  document.addEventListener("attested:lang", function (event) {
    var lang = event.detail && event.detail.lang || "en";
    translate(lang);
    paintHubSignalLabels(lang);
  });
})();
