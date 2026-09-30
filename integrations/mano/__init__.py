"""Typed, time-versioned MANO/Kubernetes relationships; no automatic remediation."""

RELATIONS={'contains','hosts','member_of','calls','depends_on'}
ENTITY_TYPES={'mano','site','vim','cluster','cnf','vnf','vdu','cnfc','vnfc','pod','container','node','service','database'}


def validate_inventory(entities,edges):
    by_id={e['entity_id']:e for e in entities}
    if len(by_id)!=len(entities): raise ValueError('Duplicate entity identity')
    for e in entities:
        if e['entity_type'] not in ENTITY_TYPES: raise ValueError('Unknown entity type')
    for edge in edges:
        if edge['relation'] not in RELATIONS: raise ValueError('Unknown relationship')
        if edge['source'] not in by_id or edge['target'] not in by_id: raise ValueError('Orphan edge')
        if edge['valid_from']>=edge['valid_to']: raise ValueError('Invalid topology interval')
        if edge['relation']=='hosts' and by_id[edge['source']]['entity_type']!='node':
            raise ValueError('hosts relation must originate at node')
    return True


def as_of(edges,event_time,cutoff):
    return [e for e in edges if e['valid_from']<=event_time<e['valid_to'] and e['available_at']<=cutoff]


def influence_edges(edges):
    """Convert typed observed relations into a propagation heuristic, not a causal graph."""
    result=[]
    for edge in edges:
        r=dict(edge)
        if r['relation'] in ('calls','depends_on'):
            r['source'],r['target']=r['target'],r['source']
        elif r['relation']!='hosts':
            continue  # containment alone does not establish failure propagation
        result.append(r)
    return result
