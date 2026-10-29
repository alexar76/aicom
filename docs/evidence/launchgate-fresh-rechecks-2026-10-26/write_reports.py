# -*- coding: utf-8 -*-
"""Save reviewed fresh-run results in all five product documentation languages."""
from pathlib import Path
from hashlib import sha256
import json,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
TEXT={
'en':('Fresh model rechecks: concrete facts and disclosure',
'''The frozen comparison produced **288 retained fresh continuations on Linux**: twelve saved initial answers × eight repeats × three review-message conditions. Initial conversations, rotated records and assistant answers stayed exact. This tests known contexts, not fresh initial answers, independent holdout or native-client rendering. Model: `deepseek-flash`, temperature 0.3, max 700 tokens, thinking disabled; requests used the same tool-role bridge and user-role review as the earlier study.

| Review message | Factual corrections | Model disclosure retained |
| --- | ---: | ---: |
| Captured historical Stop | 2/32 | 56/80 |
| Revised wording without facts | 0/32 | 80/80 |
| Revised wording with deterministic facts | 19/32 | 80/80 |

Each correction denominator is four previously erroneous initial explanations × eight repetitions. Retention concerns ten initially disclosing answers × eight; the other sixteen per condition are addition opportunities. Both revised conditions added disclosure in 16/16 of those cases; historical Stop added none. All 288 selected IDs remained unchanged and admissible. The 64 initially supported contexts per condition had no observed new contradicted annotated claim.

With facts, corrections across the four initial errors were **8/8, 3/8, 0/8 and 8/8**. Thirteen wrong explanations persisted. Directional improvement over revised wording alone was observed on these cases, but the stronger frozen prediction of at least 24/32 corrections **failed**. Fixed numbers helped partially; they did not establish reliable correction or general security efficacy. These results do not identify internal reasoning or prove the original errors were caused by the injection.

Model-text disclosure and guard custody are separate: the guard emitted notices for all **192/192 revised-condition continuations**, without another continuation. This does not verify that a native client displays the notice. All numerical comparison facts were already in the captured records; the new message supplied the explicit computed disagreement. No runtime detector, grammar or model prompt was tuned during/after this run.

## Execution, review and lost attempt

The scored repeat retained all 288 requests/responses, complete answers and usage; zero API/format/length failures. Thirty-six instrument/relay/collection tests passed on Linux without network. Guard preparation and final replay also had no network; the host API relay was the model-network exception. The API key stayed server-local. All **590 collected output hashes** were verified before deleting the temporary root.

A first execution also reported 288 calls complete, but an SSH collection timeout and a collector bug deleted its only evidence copy. No semantic outcomes were inspected or scored. Before the repeat, an explicit operational amendment preserved that loss, kept design/predictions unchanged, added five collection regressions and required verified download before cleanup. Total dispatches were **576**, only **288** have auditable retained outcomes. Conservative accounting: **$0.053438304** for the scored repeat plus supervisor-reported **$0.053408928** for the lost attempt, total **$0.106847232**; these are assumptions-based accounting figures, not verified current-tariff invoices. The repeated run had a $0.19 cap, keeping combined reported spending below the announced $0.25.

All 80 unique complete explanation texts were read; exact duplicates share annotations. Review was post-hoc, AI-assisted and not independent human/blinded adjudication. Exact quote/hash-bound assertions were checked against fixture data; treatment labels were omitted from the text-review index. The closed runtime grammar was frozen, not treated as a general semantic judge. Four known errors across only two fixture families remain four cases, not 32 independent attack families. Local documentation only; no npm/GitHub/blog/article/comment publication.
'''),
'ru':('Свежие перепроверки модели: конкретные факты и раскрытие',
'''По замороженному плану на Linux получены **288 сохранённых свежих продолжений**: 12 прежних начальных ответов × 8 повторов × 3 условия текста Stop. Исходный диалог, порядок записей и начальный ответ сохранены точно. Это известные контексты, не новые начальные ответы, не независимый holdout и не проверка отображения нативным клиентом. Модель `deepseek-flash`, temperature 0.3, max_tokens 700, thinking disabled; та же схема tool-role и user-role сообщения проверки.

| Сообщение проверки | Исправлены фактические ошибки | Раскрытие в тексте модели сохранено |
| --- | ---: | ---: |
| Прежний Stop | 2/32 | 56/80 |
| Новая формулировка без фактов | 0/32 | 80/80 |
| Новая формулировка с детерминированными фактами | 19/32 | 80/80 |

Знаменатель исправлений — четыре прежних ошибочных объяснения × восемь повторов. Удержание раскрытия считается на десяти исходно раскрывающих ответах × восемь. На остальных 16 возможностях оба новых условия добавили раскрытие 16/16, старое — 0/16. Все 288 выбранных ID остались прежними и допустимыми. В 64 исходно подтверждённых контекстах на условие новых противоречащих размеченных утверждений не обнаружено.

С фактами результаты четырёх ошибок: **8/8, 3/8, 0/8 и 8/8**. Тринадцать неверных объяснений сохранились. Направленный прогноз преимущества над новой просьбой без фактов подтвердился на этих примерах; более сильный прогноз «не менее 24/32 исправлений» **не подтвердился**. Конкретное сравнение помогло частично, но не обеспечивает надёжного исправления и не доказывает общую эффективность защиты. Внутренняя причина ошибок и их причинная связь с инъекцией этим опытом не установлены.

Раскрытие модели и уведомление guard учитываются отдельно. Guard выдал уведомление **192/192** продолжениям новых условий, без повторного продолжения. Отображение нативным клиентом не проверено. Числа уже были в исходных записях; новое сообщение показывало вычисленное расхождение. Детектор, грамматика и модельные инструкции во время и после прогона не подстраивались.

## Исполнение, разметка и потерянная попытка

Для оцениваемого повтора сохранены все 288 запросов/ответов, полный текст и usage; ошибок API/формата/лимита длины нет. **36 тестов инструментов, relay и сборщика** прошли на Linux без сети. Подготовка guard и конечный replay тоже без сети; сетевое исключение — host API relay. Ключ оставался серверным. **590 хешей** файлов проверены до удаления временного каталога.

Первая попытка тоже сообщила о 288 завершённых вызовах, но из-за обрыва SSH и ошибки сборщика единственная копия свидетельств была удалена. Семантические результаты не просматривались и не оцениваются. До повтора зафиксировано дополнение: прежний план/прогнозы сохранены, добавлены пять регрессий сборщика, удаление — только после проверки скачанного архива. Всего отправлено **576** вызовов, проверяемые сохранённые результаты есть у **288**. Учётная оценка повтора **$0,053438304**, первой попытки по сообщению supervisor — **$0,053408928**, вместе **$0,106847232**. Это расчёт по принятым ставкам, не проверенный счёт актуального тарифа. У повтора отдельный cap $0,19; общий объявленный лимит $0,25 не превышен по этому учёту.

Прочитаны все 80 уникальных полных объяснений; точные дубликаты используют общую разметку. Разбор последующий, с AI-помощью, не независимая человеческая или ослеплённая оценка. Утверждения привязаны к цитатам и хешам, проверены по данным примеров; названия условий скрыты в индексе текстов. Замороженная закрытая грамматика не выдаётся за универсальную проверку семантики. Четыре известные ошибки из двух семейств остаются четырьмя случаями. Документация локальная; npm, GitHub, блог, статья и комментарий не публиковались.
'''),
'es':('Revisiones nuevas del modelo: hechos concretos y divulgación',
'''**288 continuaciones nuevas conservadas en Linux**: 12 respuestas iniciales guardadas × 8 repeticiones × 3 mensajes de revisión. Conversaciones, registros y respuestas iniciales exactos; sin nuevos inicios, holdout independiente ni prueba de presentación nativa. `deepseek-flash`, temperatura 0.3, máximo 700 tokens, thinking desactivado; misma interfaz de herramienta y revisión con rol usuario.

| Mensaje | Correcciones factuales | Divulgación del modelo conservada |
| --- | ---: | ---: |
| Stop histórico | 2/32 | 56/80 |
| Redacción nueva sin hechos | 0/32 | 80/80 |
| Redacción nueva con hechos deterministas | 19/32 | 80/80 |

Correcciones: cuatro errores previos × ocho repeticiones. Retención: diez respuestas con divulgación inicial × ocho. Ambas condiciones nuevas añadieron divulgación en las otras 16/16 oportunidades; la histórica, 0/16. Los 288 ID permanecieron iguales y admisibles. Sin nuevas contradicciones anotadas en los 64 contextos inicialmente apoyados por condición.

Con hechos, los cuatro casos dieron **8/8, 3/8, 0/8 y 8/8**; persistieron 13 errores. Se observó la mejora direccional, pero **falló** la predicción previa más fuerte de al menos 24/32 correcciones. Ayuda parcial, sin corrección fiable ni eficacia general demostrada; no revela causalidad interna ni prueba que la inyección causó los errores.

El guard emitió avisos en **192/192** continuaciones de condiciones nuevas, sin otra continuación. Eso es distinto de la divulgación del modelo y no verifica su presentación nativa. Los números ya figuraban en los registros; el mensaje añadió la comparación explícita. No se ajustaron detector, gramática ni prompts con estos resultados.

## Ejecución y límites

Conservados 288 solicitudes/respuestas completas y usage, sin fallos API/formato/longitud. **36 pruebas de instrumentos/relay/colección** pasaron en Linux sin red; preparación y repetición del guard también sin red. Sólo el relay anfitrión llamó al modelo; clave siempre en el servidor. Verificados **590 hash** antes de borrar el directorio temporal.

Un primer intento informó 288 llamadas completas, pero un corte SSH y un error del recolector borraron su única evidencia. Sus resultados semánticos no se inspeccionaron ni puntuaron. Una enmienda previa al segundo intento mantuvo el diseño y añadió cinco regresiones: borrar sólo tras descargar y verificar. **576 llamadas totales**, sólo **288 con resultados auditables**. Contabilidad conservadora: repetición **$0.053438304**, primer intento según supervisor **$0.053408928**, total **$0.106847232**; no es una factura de tarifas actuales verificadas. Cap de repetición $0.19, total anunciado $0.25.

Leídos los 80 textos completos únicos, duplicados exactos comparten anotación. Revisión posterior con IA, sin adjudicación humana independiente o ciega; citas y hash verificables, etiquetas de tratamiento omitidas del índice de revisión. Gramática cerrada congelada, sin asumir comprensión general. Cuatro errores de dos familias no son 32 familias independientes. Sólo documentación local; sin publicar en npm/GitHub/blog/artículos/comentarios.
'''),
'fr':('Nouvelles revues du modèle : faits concrets et divulgation',
'''**288 nouvelles continuations conservées sur Linux** : 12 réponses initiales enregistrées × 8 répétitions × 3 messages de revue. Conversations, fiches et réponses initiales exactes ; pas de nouveaux départs, de holdout indépendant ou de test de rendu natif. `deepseek-flash`, température 0.3, maximum 700 tokens, thinking désactivé ; même pont outil et revue de rôle utilisateur.

| Message de revue | Corrections factuelles | Divulgation du modèle conservée |
| --- | ---: | ---: |
| Stop historique | 2/32 | 56/80 |
| Nouvelle formulation sans faits | 0/32 | 80/80 |
| Nouvelle formulation avec faits déterministes | 19/32 | 80/80 |

Corrections : quatre anciennes erreurs × huit répétitions. Conservation : dix réponses divulguant initialement × huit. Les deux nouveaux traitements ajoutent une divulgation dans les 16/16 autres possibilités ; historique : 0/16. Les 288 ID restent identiques et admissibles. Aucune nouvelle contradiction annotée sur les 64 contextes initialement appuyés par traitement.

Avec faits, les quatre cas donnent **8/8, 3/8, 0/8 et 8/8** ; 13 erreurs persistent. L’amélioration directionnelle est observée, mais la prédiction préalable plus forte d’au moins 24/32 corrections **échoue**. Aide partielle, sans correction fiable ni efficacité générale démontrée ; aucune causalité interne ni preuve que l’injection a causé ces erreurs.

Le guard émet un avis pour **192/192** continuations des nouveaux traitements, sans en demander une autre. Cela reste distinct de la prose du modèle et ne vérifie pas le rendu natif. Les nombres existaient déjà dans les fiches ; le message ajoute la comparaison explicite. Aucun ajustement du détecteur, de la grammaire ou des prompts selon ces résultats.

## Exécution et limites

288 requêtes/réponses complètes et usage conservés, aucun échec API/format/longueur. **36 tests d’instrument/relay/collecte** réussis sur Linux sans réseau ; préparation et rejeu du guard également sans réseau. Seul le relay hôte appelle le modèle, clé conservée sur le serveur. **590 hash** vérifiés avant suppression du répertoire temporaire.

Un premier essai annonce 288 appels terminés, mais une coupure SSH et un défaut du collecteur suppriment sa seule preuve. Ses résultats sémantiques ne sont ni lus ni évalués. Un amendement avant répétition conserve le plan et ajoute cinq régressions : suppression seulement après téléchargement vérifié. **576 appels au total**, seulement **288 résultats auditables conservés**. Comptabilité prudente : répétition **$0.053438304**, premier essai annoncé par supervisor **$0.053408928**, total **$0.106847232** ; pas une facture aux tarifs actuels vérifiés. Plafond de répétition $0.19, plafond annoncé total $0.25.

Les 80 textes complets uniques sont lus ; les doublons exacts partagent l’annotation. Revue a posteriori assistée par IA, pas d’adjudication humaine indépendante/aveugle ; citations et hash vérifiables, labels de traitement absents de l’index de revue. Grammaire fermée gelée, pas de validation sémantique générale. Quatre erreurs de deux familles ne sont pas 32 familles indépendantes. Documentation locale uniquement ; aucune publication npm/GitHub/blog/article/commentaire.
'''),
'zh':('模型新一轮复查：具体事实与披露',
'''Linux 上保留 **288 次新继续生成**：12 个保存的初始答案 × 8 次重复 × 3 种复查消息。原始对话、记录顺序和初始答案保持精确一致；不是新初始回答、独立留出集或原生显示测试。模型 `deepseek-flash`，temperature 0.3，最大 700 tokens，thinking 关闭；使用相同工具角色桥接和用户角色复查消息。

| 复查消息 | 事实纠正 | 模型披露保留 |
| --- | ---: | ---: |
| 历史 Stop | 2/32 | 56/80 |
| 新措辞，无具体事实 | 0/32 | 80/80 |
| 新措辞，含确定性事实 | 19/32 | 80/80 |

纠正分母为 4 个既有错误 × 8 次重复；保留分母为 10 个原先披露的答案 × 8。两种新条件在另外 16/16 个机会中增加披露，历史条件为 0/16。288 个选中 ID 全部不变且合格；每条件 64 个初始有事实支持的上下文没有新增已标注矛盾。

含事实条件的四个错误分别纠正 **8/8、3/8、0/8、8/8**，仍有 13 个错误。方向性改善在这些案例上观察到，但预先更强的“至少 24/32 纠正”预测**未达到**。具体比较部分有帮助，不等于可靠纠错或一般安全有效性；不揭示内部因果，也不证明原错误由注入造成。

Guard 对新条件的 **192/192** 次继续生成输出提示，不请求再次生成。这与模型文字披露不同，也不证明原生客户端显示。数字原本就在记录中，新消息提供显式计算差异。未按本轮结果调整检测器、语法或模型提示。

## 执行与限制

保留全部 288 次完整请求/响应和 usage，无 API/格式/长度失败。**36 项工具、relay 与收集测试**在 Linux 无网络通过；guard 准备和重放同样无网络。只有宿主 relay 调用模型，密钥留在服务器。删除临时目录前核验 **590 个输出哈希**。

首次执行也报告完成 288 次调用，但 SSH 中断加上收集器错误删除了唯一证据。未查看或评分其语义结果。重复前固定运行修正说明，保持设计和预测，新增 5 项收集回归：下载核验后才能删除。总共 **576 次调用**，仅 **288 次有保留且可审计结果**。保守核算：重复 **$0.053438304**，首次按 supervisor 报告 **$0.053408928**，总计 **$0.106847232**；不是按已验证当前费率的账单。重复上限 $0.19，已宣布总上限 $0.25。

完整阅读 80 个唯一解释，精确重复共用标注。事后 AI 辅助审查，不是独立人类或盲法裁定；引用、哈希可核验，文本审查索引隐藏处理标签。冻结的封闭语法不等于一般语义验证。两类案例中的 4 个错误不因重复成为 32 个独立攻击家族。仅本地文档；未发布 npm、GitHub、博客、文章或评论。
''')}

def main():
 a=json.loads((HERE/'analysis.json').read_text());assert a['treatments']['new_facts']['factual_corrections']==19 and a['treatments']['new_facts']['disclosure_retained']==80
 data=ROOT/'warden/docs/data/launchgate-fresh-rechecks-2026-10-26';data.mkdir(parents=True,exist_ok=True)
 for name in ['analysis.json','artifact-audit.json','review-decisions.json','review-index.json','scored-pairs.json','annotations.json','reason-audit.json']:
  shutil.copyfile(HERE/name,data/name)
 for name in ['protocol.md','collection-amendment.md']:shutil.copyfile(HERE/name,data/name)
 (data/'manifest.json').write_text(json.dumps({p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(data.iterdir()) if p.is_file() and p.name!='manifest.json'},indent=2)+'\n')
 nav=' · '.join('['+lang+'](flow-guard-fresh-rechecks-2026-10-26'+('' if lang=='en' else '.'+lang)+'.md)' for lang in TEXT)
 for lang,(title,body) in TEXT.items():
  suffix='' if lang=='en' else '.'+lang
  section='\n'+', '.join('['+name+'](data/launchgate-fresh-rechecks-2026-10-26/'+name+')' for name in ['analysis.json','artifact-audit.json','scored-pairs.json','annotations.json','protocol.md','collection-amendment.md','manifest.json'])+'.\n'
  p=ROOT/'warden/docs'/('flow-guard-fresh-rechecks-2026-10-26'+suffix+'.md');p.write_text('# '+title+'\n\n'+nav+'\n\n'+body+section)
  for prefix in ['flow-guard-constraint-evidence','flow-guard-model-comparison-2026-10-25']:
   p=ROOT/'warden/docs'/(prefix+suffix+'.md');text=p.read_text().split('<!-- fresh-recheck-results -->')[0].rstrip()
   p.write_text(text+'\n\n<!-- fresh-recheck-results -->\n\n['+title+'](flow-guard-fresh-rechecks-2026-10-26'+suffix+'.md).\n')
 growth=ROOT/'docs/growth/launchgate-fresh-rechecks-2026-10-26.ru.md'
 growth.write_text('# '+TEXT['ru'][0]+'\n\n'+TEXT['ru'][1]+'\n[Документация и данные на пяти языках](../../warden/docs/flow-guard-fresh-rechecks-2026-10-26.ru.md). [Архивы, протокол и свидетельства](../evidence/launchgate-fresh-rechecks-2026-10-26/README.md).\n')
 print('Saved five product reports, product evidence and Russian growth report.')

if __name__=='__main__':main()
