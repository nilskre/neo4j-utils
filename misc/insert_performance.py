#!/usr/bin/env python

import random
import string
import math

import tqdm

import neo4j_utils


def rstring(l = 10, lower = False, title = False, upper = False):
    """
    Create a random string of a given length and capitalization.
    """

    charclass = 'lowercase' if lower else 'uppercase' if upper else 'letters'

    chars = getattr(string, f'ascii_{charclass}')

    result = ''.join(random.sample(chars, l))

    result = result.capitalize() if title else result

    return result


def unique_labels(n, **kwargs):
    """
    Create a set with the desired number of unique random strings.
    """

    result = set()

    for i in range(int(1e4)):

        result.update({rstring(**kwargs) for _ in range(int(1e4))})

        if len(result) >= n:

            break

    return list(result)[:int(n)]


def random_nodes(n = 1e5, nlabels = 1) -> list[dict[str, str]]:
    """
    A list of dicts, each dict represents a node, consisting of an `ID`
    and a `label`.
    """

    labels = {
        rstring(l = 10, lower = True, title = True)
        for _ in range(nlabels)
    }

    result = []

    ids = k_ids(n, nlabels)

    for label, _ids in zip(labels, ids):

        result.extend(
            {
                'label': label,
                'ID': _id,
            }
            for _id in _ids
        )

    return result[:int(n)]


def random_rels(nrels = 2e6, nnodes = 1e6, ntypes = 1, nlabels = 1):
    """
    A list of dicts, each represents a relation with the labels and IDs of
    the source and target nodes, the ID and type of the relation.
    """

    types = [
        rstring(l = 5).upper()
        for _ in range(ntypes)
    ]

    nodes = (
        nnodes
            if isinstance(nnodes, list) else
        random_nodes(nnodes, nlabels = nlabels)
    )

    ids = k_ids(nrels, ntypes)

    result = []

    for reltype, _ids in zip(types, ids):

        counts = [10] * len(nodes)

        result.extend(
            {
                'source_label': anode['label'],
                'target_label': bnode['label'],
                'source_id': anode['ID'],
                'target_id': bnode['ID'],
                'ID': _id,
                'rel_type': reltype,
            }
            for anode, bnode, _id in zip(
                random.sample(nodes, len(_ids), counts = counts),
                random.sample(nodes, len(_ids), counts = counts),
                _ids,
            )
        )

    return result


def k_ids(total, k = 1, **kwargs) -> list[list[str]]:
    """
    `k` lists with `total / k` unique random strings in each. In other words,
    `total` number of unique random strings divided into `k` equal size
    batches.
    """

    ids = unique_labels(n = total, **kwargs)

    chunk_size = math.ceil(total / k)

    return list(chunks(ids, chunk_size, pbar = False))


def chunks(lst, n, pbar = True):
    """
    Yields successive `n`-sized chunks from `lst`.
    """

    it = range(0, len(lst), int(n))
    it = tqdm.tqdm(it) if pbar else it

    for i in it:

        yield lst[i:i + int(n)]



def insert0(driver, data = None, batch_size = 1.5e4, **kwargs):

    data = data or random_rels(**kwargs)

    for batch in chunks(data, batch_size):

        driver.query(
            """
            UNWIND $entities AS ent
            MERGE (s:Anything {ID: ent.source_id})
            MERGE (t:Anything {ID: ent.target_id})
            MERGE (s)-[rel:Rel]->(t)
            set rel.ID = ent.ID
            """,
            parameters = {'entities': batch},
        )


def insert1(driver, data = None, batch_size = 1.5e4, **kwargs):

    data = data or random_rels(**kwargs)

    nodes = list(sorted(
        {d['source_id'] for d in data} |
        {d['target_id'] for d in data}
    ))

    driver.query('CREATE INDEX node_id IF NOT EXISTS FOR (n:Anything) ON (n.ID)')
    driver.query('CREATE LOOKUP INDEX node_la IF NOT EXISTS FOR (n) ON EACH labels(n)')
    # this is slower:
    # driver.query('CREATE CONSTRAINT node_cs IF NOT EXISTS ON (n:Anything) ASSERT n.ID IS UNIQUE;')
    driver.query('CREATE INDEX rel_id IF NOT EXISTS FOR ()-[r:Rel]->() ON (r.ID)')
    driver.query('CREATE LOOKUP INDEX rel_ty IF NOT EXISTS FOR ()-[r]->() ON type(r)')
    driver.query('CALL db.awaitIndexes()')

    for batch in chunks(nodes, batch_size):

        batch = [{'node_id': x} for x in batch]

        driver.query(
            """
            UNWIND $entities AS ent
            MERGE (n:Anything {ID: ent.node_id})
            """,
            parameters = {'entities': batch},
        )

    print('Creating node text index.')
    driver.query('CREATE TEXT INDEX node_it IF NOT EXISTS FOR (n:Anything) ON (n.ID)')
    driver.query('CALL db.awaitIndexes()')

    data = list(sorted(
        data,
        key = lambda r: (r['source_id'], r['target_id'])
    ))

    for batch in chunks(data, batch_size):

        driver.query(
            """
            UNWIND $entities AS ent
            MATCH (s:Anything {ID: ent.source_id})
            MATCH (t:Anything {ID: ent.target_id})
            MERGE (s)-[rel:Rel]->(t)
            set rel.ID = ent.ID
            """,
            parameters = {'entities': batch},
        )

    print('Creating rel text index.')
    driver.query('CREATE TEXT INDEX rel_it IF NOT EXISTS FOR ()-[r:Rel]->() ON (r.ID)')
    driver.query('CALL db.awaitIndexes()')


def insert2(driver, data = None, batch_size = 1.5e4, **kwargs):

    data = data or random_rels(**kwargs)

    nodes = list(
        {d['source_id'] for d in data} |
        {d['target_id'] for d in data}
    )

    # driver.query('CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Anything) REQUIRE n.ID IS UNIQUE')
    driver.query('CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Anything) REQUIRE n.ID IS NODE KEY')
    driver.query('CREATE INDEX rel_id IF NOT EXISTS FOR ()-[r:Rel]->() ON (r.ID)')
    driver.query('CREATE LOOKUP INDEX rel_ty IF NOT EXISTS FOR ()-[r]->() ON type(r)')
    driver.query('CALL db.awaitIndexes()')

    for batch in chunks(nodes, batch_size):

        batch = [{'node_id': x} for x in batch]

        driver.query(
            """
            UNWIND $entities AS ent
            MERGE (n:Anything {ID: ent.node_id})
            """,
            parameters = {'entities': batch},
        )

    for batch in chunks(data, batch_size):

        driver.query(
            """
            UNWIND $entities AS ent
            MATCH (s:Anything {ID: ent.source_id})
            MATCH (t:Anything {ID: ent.target_id})
            MERGE (s)-[rel:Rel]->(t)
            set rel.ID = ent.ID
            """,
            parameters = {'entities': batch},
        )


def main(driver_args = None, **kwargs):

    driver = neo4j_utils.Driver(**(driver_args or {}))
    driver.wipe_db()
    driver.drop_indices_constraints()

    insert1(driver, **kwargs)
