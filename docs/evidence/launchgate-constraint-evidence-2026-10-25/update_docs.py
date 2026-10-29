# -*- coding: utf-8 -*-
"""Reconcile verified Linux results into the five-language product documentation."""
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
TEXT={
'en':('Linux validation — 26 October 2026', '''Build and typecheck passed, together with **743 WARDEN tests in 21 files** (including 29 new constraint/continuation tests), **24 Python instrument tests** and the existing **28-scenario deterministic gate**. All 276 collected output hashes were verified. Runtime checks had no network; only npm dependency installation had network. The temporary remote root was removed. The local build and plugin were synchronized from these Linux-generated outputs, after rechecking frozen source hashes.

| Saved-answer observation | Result |
| --- | ---: |
| Actual initial/final pairs replayed | 12 |
| Explicit eligible sets with a $190 item despite the $150 limit | 4 |
| Same contradictions still present in the unchanged old final answers | 4 |
| Continuation hook outputs retaining the guard instruction notice | 12/12 |
| Prior model-text disclosure losses accompanied by that guard notice | 3/3 |
| Second continuations requested / new model calls | 0 / 0 |

The adapter's grammar was written after seeing these saved answers; this is **post-hoc development-case replay**, not independent semantic validation or a holdout. It independently extracts claim lists at execution time without reading the gold labels, then the replay compares detections with the earlier audit. Finding all four contradictions does not validate all prose or establish a general false-positive rate. The four original wrong explanations were not regenerated or corrected in this replay. Three model prose disclosures remain absent: the new safeguard is an independently emitted hook notice, whose client-side display must still be verified. New model correction and held-out efficacy remain unmeasured.
'''),
'ru':('Проверка на Linux — 26 октября 2026', '''Сборка и проверка типов прошли, как и **743 теста WARDEN в 21 файле** (в том числе 29 новых проверок ограничений и продолжений), **24 Python-теста инструментов** и существующий **детерминированный gate из 28 сценариев**. Проверены все 276 хешей собранных файлов. Runtime-проверки выполнялись без сети; сеть была только у установки npm-зависимостей. Временный каталог сервера удалён. Локальная сборка и plugin синхронизированы из результатов Linux после проверки совпадения исходников с замороженным манифестом.

| Наблюдение на сохранённых ответах | Результат |
| --- | ---: |
| Повторены реальные пары начального/конечного ответа | 12 |
| Найден ошибочный допустимый набор с объектом за $190 при лимите $150 | 4 |
| Противоречия сохраняются в неизменных прежних конечных ответах | 4 |
| Выход hook после продолжения сохраняет уведомление guard об инструкции | 12/12 |
| Прежние потери раскрытия в тексте модели сопровождаются уведомлением guard | 3/3 |
| Запрошено вторых продолжений / новых вызовов модели | 0 / 0 |

Грамматика адаптера написана после знакомства с этими ответами: это **последующий повтор известных случаев разработки**, не независимая семантическая проверка и не holdout. При исполнении списки утверждений извлекаются без золотых меток, затем результат сравнивается с прежним разбором. Обнаружение всех четырёх противоречий не подтверждает всю прозу и не оценивает общую частоту ложных тревог. Четыре ошибочных объяснения в этом повторе не перегенерированы и не исправлены. В трёх текстах модели раскрытие по-прежнему отсутствует: новая защита — отдельное уведомление hook, показ которого клиентом ещё надо проверить. Исправления моделью и эффективность на отложенных примерах не измерены.
'''),
'es':('Validación Linux — 26 de octubre de 2026', '''Compilación y tipos correctos: **743 pruebas WARDEN en 21 archivos**, incluidas 29 nuevas; **24 pruebas Python** y el **gate determinista existente de 28 escenarios**. Verificados los 276 hash de salida. Pruebas sin red; sólo la instalación de dependencias npm tuvo red. Directorio remoto temporal eliminado. Compilado local y plugin sincronizados desde Linux tras verificar las fuentes congeladas.

| Observación sobre respuestas guardadas | Resultado |
| --- | ---: |
| Parejas inicial/final reales repetidas | 12 |
| Conjuntos admisibles falsos con $190 pese al límite de $150 | 4 |
| Contradicciones restantes en respuestas finales antiguas intactas | 4 |
| Avisos del guard conservados en la salida de continuación | 12/12 |
| Pérdidas previas de divulgación del modelo acompañadas por aviso | 3/3 |
| Segundas continuaciones / nuevas llamadas al modelo | 0 / 0 |

La gramática se escribió tras conocer estas respuestas: **repetición posterior de casos de desarrollo**, sin validación semántica independiente ni holdout. La extracción no lee las etiquetas de referencia; después se compara con la revisión previa. Detectar cuatro contradicciones no valida toda la prosa ni estima falsas alarmas generales. Las cuatro explicaciones erróneas no se regeneraron ni corrigieron. En tres textos sigue faltando divulgación: la protección nueva es el aviso separado del hook, cuya presentación por el cliente aún debe comprobarse. No se midió corrección del modelo ni eficacia independiente.
'''),
'fr':('Validation Linux — 26 octobre 2026', '''Compilation et typage réussis : **743 tests WARDEN dans 21 fichiers**, dont 29 nouveaux ; **24 tests Python** et **gate déterministe existant de 28 scénarios**. Les 276 hash de sortie ont été vérifiés. Tests sans réseau ; seule l’installation des dépendances npm utilisait le réseau. Répertoire distant temporaire supprimé. Build local et plugin synchronisés depuis Linux après vérification des sources gelées.

| Observation sur les réponses conservées | Résultat |
| --- | ---: |
| Paires initiales/finales réelles rejouées | 12 |
| Ensembles admissibles erronés avec $190 malgré le plafond $150 | 4 |
| Contradictions conservées dans les anciennes réponses finales intactes | 4 |
| Avis du guard conservés dans la sortie de continuation | 12/12 |
| Pertes antérieures de divulgation accompagnées d’un avis du guard | 3/3 |
| Secondes continuations / nouveaux appels modèle | 0 / 0 |

La grammaire a été écrite après lecture de ces réponses : **rejeu a posteriori de cas de développement**, pas de validation sémantique indépendante ni de holdout. L’extraction ne lit pas les étiquettes de référence ; ses résultats sont ensuite comparés à la revue précédente. Détecter quatre contradictions ne valide pas toute la prose et n’estime pas un taux général de faux positifs. Les quatre explications erronées ne sont ni régénérées ni corrigées. Trois textes du modèle restent sans divulgation : le nouveau contrôle est l’avis séparé du hook, dont l’affichage client reste à vérifier. Correction par le modèle et efficacité indépendante ne sont pas mesurées.
'''),
'zh':('Linux 验证 — 2026 年 10 月 26 日', '''构建和类型检查通过；**21 个文件中的 743 项 WARDEN 测试**（含 29 项新增）、**24 项 Python 工具测试**及现有 **28 场景确定性 gate** 均通过。核验全部 276 个输出哈希。运行时测试无网络，只有 npm 依赖安装联网。远端临时目录已删除。确认冻结源文件一致后，从 Linux 生成产物同步本地构建和插件。

| 保存答案上的观察 | 结果 |
| --- | ---: |
| 重放真实初始/最终答案对 | 12 |
| 在 $150 上限下声称 $190 项合格的错误集合 | 4 |
| 未改动旧最终答案中仍存在的矛盾 | 4 |
| 继续生成后 hook 输出保留 guard 指令提示 | 12/12 |
| 原先模型文字披露丢失、现在伴随 guard 提示 | 3/3 |
| 请求第二次继续生成 / 新增模型调用 | 0 / 0 |

适配器语法在阅读这些答案后编写：这是**开发案例的事后重放**，不是独立语义验证或留出集。运行时提取不读取金标，之后再与先前审查比较。发现 4 个矛盾不代表全文正确，也不估计一般误报率。4 个错误解释没有重新生成或被纠正；3 个模型文本仍缺少披露。新增保障是独立 hook 提示，其客户端实际显示仍需验证。模型纠错和独立泛化有效性均未测量。
''')}

def main():
 r=json.loads((HERE/'run-01/out/replay.json').read_text()); e=json.loads((HERE/'run-01/execution.json').read_text())
 assert r['summary']['deterministicContradictions']==4 and e['cleanup']['absent'] and all(c['exitCode']==0 for c in e['checks'])
 for lang,(title,body) in TEXT.items():
  suffix='' if lang=='en' else '.'+lang
  p=ROOT/'warden/docs'/('flow-guard-constraint-evidence'+suffix+'.md')
  text=p.read_text().split('## '+title)[0]
  cut={
   'en':'Build/runtime tests and the saved-pair replay require Linux validation.',
   'ru':'Сборка, runtime-тесты и повтор сохранённых пар требуют проверки на Linux;',
   'es':'La compilación, pruebas y repetición requieren validación en Linux;',
   'fr':'Compilation, tests et rejeu nécessitent une validation Linux ;',
   'zh':'构建、测试和保存答案重放需在 Linux 验证；',
  }[lang]
  text=text.split(cut)[0].rstrip()
  section='## '+title+'\n\n'+body
  provenance={'en':'Development and review used AI assistance; no independent blinded semantic review is claimed.','ru':'Разработка и разбор выполнены с AI-помощью; независимая ослеплённая семантическая проверка не заявлена.','es':'Desarrollo y revisión con ayuda de IA; sin revisión semántica independiente y ciega.','fr':'Développement et revue assistés par IA ; aucune revue sémantique indépendante en aveugle.','zh':'开发和审查使用 AI 辅助；不声称独立盲法语义评审。'}
  section+='\n'+provenance[lang]+'\n'
  section+='\n'+', '.join('['+name+'](data/launchgate-constraint-evidence-2026-10-26/'+name+')' for name in ['results.json','cases.json','execution.json','input-manifest.json','manifest.json'])+'.\n'
  p.write_text(text+'\n\n'+section)
  p=ROOT/'warden/docs'/('flow-guard-model-comparison-2026-10-25'+suffix+'.md')
  text=p.read_text().split('<!-- constraint-evidence-runtime-followup -->')[0].rstrip()
  p.write_text(text+'\n\n<!-- constraint-evidence-runtime-followup -->\n\n['+title+'](flow-guard-constraint-evidence'+suffix+'.md).\n')
 print('Updated verified result sections in five product documents and five comparison links.')

if __name__=='__main__': main()
