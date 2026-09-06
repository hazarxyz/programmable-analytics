-- All finalized V4 transfers to the burn address on Robinhood Chain.
-- One log request. Block timestamps use Dune when indexed, otherwise one RPC read.
WITH rpc_response AS (
    SELECT reply
    FROM UNNEST(ARRAY[json_parse(http_post(
        'https://rpc.mainnet.chain.robinhood.com',
        '{"jsonrpc":"2.0","id":1,"method":"eth_getLogs","params":[{"fromBlock":"0x0","toBlock":"finalized","address":"0xc60ba256b44334a0cd2c7242e98b88f031abb006","topics":["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",null,"0x000000000000000000000000000000000000000000000000000000000000dead"]}]}',
        ARRAY['Content-Type: application/json']
    ))]) AS r(reply)
), log_documents AS (
    SELECT document
    FROM rpc_response
    CROSS JOIN UNNEST(CAST(json_parse(
        CASE WHEN substr(json_format(json_extract(reply, '$.result')), 1, 1) = '['
             THEN json_format(json_extract(reply, '$.result'))
             ELSE concat('RPC_LOGS_ERROR: ', json_format(reply))
        END
    ) AS ARRAY(JSON))) AS l(document)
), decoded AS (
    SELECT
        varbinary_to_uint256(from_hex(substr(json_extract_scalar(document, '$.data'), 3))) AS amount_raw,
        varbinary_substring(from_hex(substr(json_extract_scalar(document, '$.topics[1]'), 3)), 13, 20) AS sender,
        from_hex(substr(json_extract_scalar(document, '$.transactionHash'), 3)) AS tx_hash,
        from_base(substr(json_extract_scalar(document, '$.blockNumber'), 3), 16) AS block_number,
        from_base(substr(json_extract_scalar(document, '$.logIndex'), 3), 16) AS log_index
    FROM log_documents
    WHERE lower(json_extract_scalar(document, '$.address')) = '0xc60ba256b44334a0cd2c7242e98b88f031abb006'
      AND json_extract_scalar(document, '$.topics[0]') = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
      AND json_extract_scalar(document, '$.topics[2]') = '0x000000000000000000000000000000000000000000000000000000000000dead'
      AND COALESCE(json_extract_scalar(document, '$.removed'), 'false') = 'false'
), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY tx_hash, log_index ORDER BY block_number) AS duplicate_rank
    FROM decoded
    WHERE amount_raw > UINT256 '0'
), timed AS (
    SELECT r.amount_raw, r.sender, r.tx_hash, r.block_number, r.log_index,
        indexed.indexed_time, block_response
    FROM ranked r
    LEFT JOIN (
        SELECT tx_hash, "index" AS log_index, max(block_time) AS indexed_time
        FROM robinhood.logs
        WHERE contract_address = 0xc60ba256b44334a0cd2c7242e98b88f031abb006
          AND topic0 = 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
          AND topic2 = 0x000000000000000000000000000000000000000000000000000000000000dead
        GROUP BY tx_hash, "index"
    ) indexed ON indexed.tx_hash = r.tx_hash AND indexed.log_index = r.log_index
    CROSS JOIN UNNEST(ARRAY[
        CASE WHEN indexed.indexed_time IS NULL THEN json_parse(http_post(
            'https://rpc-robinhood.blockmachine.io',
            concat('{"jsonrpc":"2.0","id":1,"method":"eth_getBlockByNumber","params":["0x', to_base(r.block_number, 16), '",false]}'),
            ARRAY['Content-Type: application/json']
        )) ELSE CAST(NULL AS JSON) END
    ]) AS b(block_response)
    WHERE r.duplicate_rank = 1
), timestamps AS (
    SELECT *,
        CASE WHEN indexed_time IS NULL THEN
            from_base(coalesce(substr(json_extract_scalar(block_response, '$.result.timestamp'), 3), 'RPC_TIMESTAMP_MISSING'), 16)
        END AS rpc_timestamp
    FROM timed
), burns AS (
    SELECT amount_raw, sender, tx_hash, block_number, log_index,
        coalesce(indexed_time, CAST(from_unixtime(
            CASE WHEN rpc_timestamp > 0 THEN rpc_timestamp
                 ELSE from_base(concat('RPC_TIMESTAMP_INVALID_', coalesce(CAST(rpc_timestamp AS VARCHAR), 'NULL')), 16)
            END
        ) AT TIME ZONE 'UTC' AS TIMESTAMP)) AS burn_time,
        row_number() OVER (PARTITION BY tx_hash ORDER BY log_index) AS tx_rank
    FROM timestamps
), metrics AS (
    SELECT *,
        sum(amount_raw) OVER () AS total_raw,
        sum(amount_raw) OVER (ORDER BY block_number, log_index ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_raw,
        sum(CASE WHEN tx_rank = 1 THEN 1 ELSE 0 END) OVER () AS burn_transactions
    FROM burns
)
SELECT burn_time AS burn_time_utc,
    CAST(amount_raw AS DOUBLE) / 1e18 AS v4_burned,
    get_href(concat('https://robinhoodchain.blockscout.com/address/0x', lower(to_hex(sender))), concat('0x', substr(lower(to_hex(sender)), 1, 6), '...', substr(lower(to_hex(sender)), 36, 5))) AS sender,
    get_href(concat('https://robinhoodchain.blockscout.com/tx/0x', lower(to_hex(tx_hash))), 'View transaction') AS transaction,
    CAST(cumulative_raw AS DOUBLE) / 1e18 AS cumulative_v4,
    CAST(total_raw AS DOUBLE) / 1e18 AS total_v4_burned,
    CAST(total_raw AS DOUBLE) / 1e18 / 1000000000.0 * 100.0 AS supply_burned_pct,
    burn_transactions,
    concat(CAST(amount_raw / UINT256 '1000000000000000000' AS VARCHAR), '.', lpad(CAST(amount_raw % UINT256 '1000000000000000000' AS VARCHAR), 18, '0')) AS exact_v4_burned,
    CAST(amount_raw AS VARCHAR) AS amount_raw,
    concat('0x', lower(to_hex(tx_hash))) AS transaction_hash,
    block_number,
    log_index
FROM metrics
ORDER BY block_number DESC, log_index DESC
