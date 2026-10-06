"""BA/SME backlog: feature definitions are proposals, not unapproved production rules."""
from pathlib import Path
from .io import write_csv


def main():
    rows=[]
    def add(group,name,formula,unit,needs,question,cost='low',risk='Không dùng thông tin sau cutoff'):
        rows.append(dict(group=group,feature=name,formula=formula,unit=unit,grain='entity + business dimensions + window',
            suggested_windows='1m/5m/15m; confirm cadence and SLO',required_data=needs,BA_question=question,
            missing_policy='missing flag; no implicit zero',resource_cost=cost,leakage_risk=risk,
            status='PROPOSED_NEEDS_BA_AND_DATA_OWNER',owner='',approved_definition='',approved_at=''))
    for args in [
        ('APP','request_rate','delta(request_counter)/delta(t), handle reset','requests/s','request_counter + command_name','Counter cumulative? Which commands form a transaction?'),
        ('APP','error_ratio','sum(error increments)/sum(request increments)','ratio','approved code taxonomy + counters','Which type/code is technical error vs business rejection?'),
        ('APP','timeout_ratio','sum(timeout increments)/sum(request increments)','ratio','request_timeout_counter + requests','Timeout deadline and retry counting?'),
        ('APP','drop_ratio','sum(drop increments)/sum(request increments)','ratio','request_drop_counter + requests','Drop before acceptance or after?'),
        ('APP','response_request_gap','request rate - response rate aligned for latency','requests/s','request/response counters','Async completion, retry and buffering semantics?'),
        ('APP','latency_p50_p95_p99','quantile from merged bucket increment counts','ms','histogram le + bucket counters','Units, cumulative bucket semantics, success-only latency?'),
        ('APP','latency_baseline_deviation','current latency vs train/reference time-of-day median','robust z','latency + reference history','Peak/offpeak calendar and allowed windows?'),
        ('APP','exception_burst','error template count per window vs reference','events/s','log event/arrival timestamps + template','Which messages are symptom vs diagnostic evidence?'),
        ('BUSINESS','failure_by_command','error ratio grouped by approved command_name','ratio','command_name/type/code','What commands and SLAs are critical?'),
        ('BUSINESS','charging_rejection_ratio','rejections by BA-approved cause / charging attempts','ratio','CGW/ABM/PRO codes + attempts','Is BALANCE_NOT_ENOUGH expected business behavior?'),
        ('BUSINESS','recurring_result_mix','count by rec_type/rec_error_code / recurring attempts','ratio','recurring dimensions','Separate accepted recurring business outcomes from technical failure?'),
        ('BUSINESS','rating_error_mix','rating_error_code proportions per service type','ratio','rating_error_code/service_type','Stable dictionary/version for rating codes?'),
        ('BUSINESS','affected_transaction_estimate','sum affected requests under approved incident definition','transactions','request dimensions + incident scope','Impact measured per request, subscriber or transaction?'),
        ('DB','read_write_error_ratio','error increments / (error + success increments)','ratio','Aerospike operation counters','Read/write/delete denominators and retries?'),
        ('DB','db_latency_quantiles','histogram quantiles per ns/operation','ms','Aerospike latency buckets','ns is database namespace; bucket units?'),
        ('DB','memory_headroom','memory_free_pct and delta over window','percent','Aerospike memory_free_pct','Threshold differs per DB namespace?'),
        ('DB','stop_writes_duration','duration flag true / observed duration','ratio','stop_writes + clock_skew_stop_writes','Which flag has precedence and operational impact?'),
        ('DB','cluster_size_change','current size - reference expected size','nodes','cluster size + inventory','Expected planned maintenance vs unplanned shrink?'),
        ('DB','xdr_lag_retry','lag level/slope and retry counter rates','source units','XDR lag/latency/retry/dc','Lag seconds vs latency ms vs lap us; remote DC SLA?'),
        ('DB','connection_pressure','connections/approved connection capacity','ratio','client_connections + opened rate + capacity','Capacity limits and connection pooling behavior?'),
        ('CONTAINER','cpu_cores_rate','rate(container_cpu_usage_seconds_total)','cores','CPU seconds counter','Exclude infra/POD/duplicate sidecar series?'),
        ('CONTAINER','cpu_quota_ratio','cpu cores / (quota/period)','ratio','cpu usage + quota + period','Handle quota=-1 and missing period?'),
        ('CONTAINER','memory_limit_ratio','working set / positive memory limit','ratio','working_set/RSS/limit','Working set or RSS for this workload; unlimited container?'),
        ('CONTAINER','container_io_rate','delta bytes or operations / delta(t)','bytes/s or ops/s','container filesystem counters','Which devices/filesystems actually matter?'),
        ('CONTAINER','restart_or_oom_context','count observed restarts/OOM before cutoff','events','K8s events; not present in current screenshot export','Are event history and timestamps available?'),
        ('SERVER','cpu_busy_iowait','1-idle fraction; iowait fraction separately','ratio','node_cpu_seconds_total by mode/core','Which modes and CPU aggregation exclude duplicate exporters?'),
        ('SERVER','memory_available_ratio','MemAvailable / MemTotal','ratio','node memory gauges','Hardware reservation and approved operational thresholds?'),
        ('SERVER','filesystem_free_ratio','free/size by mountpoint/device','ratio','node filesystem metrics','Exclude tmpfs/overlay/ephemeral mounts?'),
        ('SERVER','disk_latency_utilization','read/write time increments / operation increments; IO busy rate','seconds/op; ratio','node disk counters','Multipath duplicates and zero-operation handling?'),
        ('TOPOLOGY','coaffected_pod_fraction','abnormal observed pods / covered pods on same node','ratio','as-of node-pod inventory + coverage','Expected shared-node interference and candidate level?'),
        ('TOPOLOGY','dependency_lag','lagged deviation between caller and dependency','seconds','as-of graph + synchronized telemetry','Clock skew bounds; correlation is not causality?'),
        ('TOPOLOGY','recent_config_change','time since authorized event before cutoff','seconds','ConfigMap/deployment/LCM history','Can change arrival time be reconstructed?'),
        ('NETWORK','endpoint_failures','error/timeout by service endpoint or port','ratio','service/endpoint mapping + call observations','Same node IP multiple ports: which service and targetPort?'),
        ('DQ','coverage_and_lag','observed/expected observations; arrival-event delay','ratio; seconds','native cadence + arrival times','Telemetry loss vs zero activity and retention policy?'),
        ('DQ','counter_reset_and_flatline','count reset; repeat runs adjusted for metric kind','count; duration','raw series + scrape metadata','Expected counter restarts, constant flags and exporter silence?'),
        ('LABEL','label_confidence_audit','coverage/age/disagreement by incident cohort','audit only','review source/status/confidence + versions','Who adjudicates root vs symptom and who approves Gold labels?'),
    ]:add(*args)
    # Label-quality fields are audit metadata, not predictors.
    for r in rows:
        if r['group']=='LABEL':r['leakage_risk']='DO NOT INCLUDE IN MODEL X; audit only'
        if r['feature'] in ('dependency_lag','latency_p50_p95_p99'):r['resource_cost']='medium; bound dimensions/windows'
    path=Path(__file__).resolve().parents[1]/'docs/BA_feature_catalog.csv'
    write_csv(path,rows);print(path)


if __name__=='__main__':main()
