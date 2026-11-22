# Hadoop pilot results

**4 of 8 selected jobs finished.** All four completed reports matched their shipped labels under the keyword scorer. Groq returned HTTP 429 for its daily token limit during the first PageRank job, before the agent produced a final report. The run stopped at that response.

## Jobs and conclusions

For each workload and class, the pilot took the first job in `abnormal_label.txt` manifest order with at least one parsed WARN, ERROR, or FATAL header in its container logs. The table follows execution order.

| Workload | Application ID | Shipped label | Keyword prediction | Exact match | Agent’s main conclusion |
|---|---|---|---|---|---|
| WordCount | `application_1445087491445_0005` | normal | normal | Yes | Most map attempts succeeded. The agent suspected a DataNode connectivity problem behind several killed attempts and left overall job success open. |
| WordCount | `application_1445087491445_0001` | machine_down | machine_down | Yes | The HDFS write pipeline marked a DataNode bad. The agent attributed the write failure to that node and left the reason for its unreachability open. |
| WordCount | `application_1445175094696_0001` | network_disconnection | network_disconnection | Yes | The agent identified an HDFS block I/O failure and an aborted task. It kept a network partition, a DataNode fault, and HDFS configuration open as explanations. |
| WordCount | `application_1445182159119_0002` | disk_full | disk_full | Yes | The map task could find no usable local output directory. The agent identified disk exhaustion as one possible cause alongside permissions and mount failure. |
| PageRank | `application_1445062781478_0011` | normal | — | Unscored | Daily token cap interrupted the investigation before a final conclusion. |
| PageRank | `application_1445062781478_0012` | machine_down | — | Unscored | Unstarted after the cap. |
| PageRank | `application_1445144423722_0020` | network_disconnection | — | Unscored | Unstarted after the cap. |
| PageRank | `application_1445182159119_0011` | disk_full | — | Unscored | Unstarted after the cap. |

## Confusion matrix

Rows are keyword predictions. Columns are shipped labels. Only completed reports enter the matrix.

| Predicted class | normal | machine_down | network_disconnection | disk_full |
|---|---:|---:|---:|---:|
| normal | 1 | 0 | 0 | 0 |
| machine_down | 0 | 1 | 0 | 0 |
| network_disconnection | 0 | 0 | 1 | 0 |
| disk_full | 0 | 0 | 0 | 1 |
| unclassified | 0 | 0 | 0 | 0 |

## Metrics

| Metric | Across 4 completed jobs |
|---|---:|
| Exact accuracy | 4/4 (100%) |
| Coarse accuracy (connectivity, disk, none) | 4/4 (100%) |
| Mean tokens (prompt + completion) | 40,247.5 |
| Mean requests | 12.25 |
| Mean tool turns | 4.75 |
| Mean elapsed time | 750.15 s |

## Limitations

- The completed sample has one WordCount job per class and zero PageRank results. Eligibility also required a warning or more severe log entry.
- The scorer uses the first matching keyword. On the normal job, “completed successfully” referred to map attempts, while the report suspected a connectivity fault. On the disk-full job, “No space left on device” appeared in a proposed diagnostic check. A class match can therefore overstate what the agent established.
- The container logs showed client-side failures and unavailable directories. The reports could not establish whether a host went down, a network link failed, or a volume ran out of space from those symptoms alone.
- The runner used an 8,000-token context budget and its existing 60-second pacing. Three completed jobs reached the six-tool-turn limit. Elapsed times include pacing, and the means exclude work spent on the interrupted fifth job.
