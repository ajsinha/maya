#!/usr/bin/env bash
# MAYA — build the estate the QA cheatsheet walks through.
#
# Every call here is one a tester can make by hand; this script exists so
# nobody has to type forty of them before reaching the interesting part.
# It is idempotent enough to re-run against a fresh database.
#
#   ./docs/QA/qa-setup.sh                       # against localhost:5006
#   MAYA_URL=http://host:5006 ./docs/QA/qa-setup.sh
set -euo pipefail

BASE="${MAYA_URL:-http://127.0.0.1:5006}"
API="$BASE/api/v1"
AUTH="${MAYA_AUTH:-admin:maya-admin-dev}"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
post() { curl -s -u "$AUTH" -X POST "$1" -H 'content-type: application/json' -d "$2"; }

say "1. people and a role"
post "$API/roles" '{"name":"feature_curator","description":"defines and loads features, nothing else","permissions":["feature:read","feature:define","feature:materialise","featureset:define"]}' >/dev/null
post "$API/principals" '{"username":"q.tester","display_name":"Q Tester","roles":["feature_curator"],"password":"qa-password-long"}' >/dev/null
post "$API/principals" '{"username":"svc/qa-runner","display_name":"QA runner","kind":"service","roles":["service"]}' >/dev/null
echo "   q.tester (feature_curator), svc/qa-runner (service)"

say "2. features — a scalar, a 12-element array, a 3x3 matrix, and a label"
post "$API/features" '{"name":"dscr","entity":"borrower","dtype":"numeric","description":"debt service coverage ratio","owner":"person/d.raman"}' >/dev/null
post "$API/features" '{"name":"ltv","entity":"borrower","dtype":"numeric","description":"loan to value","owner":"person/d.raman"}' >/dev/null
post "$API/features" '{"name":"monthly_balances","entity":"borrower","dtype":"numeric","shape":[12],"description":"twelve monthly balances","owner":"person/d.raman"}' >/dev/null
post "$API/features" '{"name":"correlation","entity":"borrower","dtype":"numeric","shape":[3,3],"description":"a 3x3 correlation matrix","owner":"person/d.raman"}' >/dev/null
post "$API/features" '{"name":"defaulted_12m","entity":"borrower","dtype":"numeric","description":"1 if the borrower defaulted within 12 months","owner":"person/d.raman"}' >/dev/null
echo "   dscr, ltv, monthly_balances[12], correlation[3,3], defaulted_12m"

say "3. views, and data in them (both clocks on every row)"
post "$API/feature-views" '{"name":"qa_borrower","entity":"borrower","owner":"person/d.raman","features":["dscr","ltv","monthly_balances","correlation"],"description":"QA borrower facts"}' >/dev/null
post "$API/feature-views/qa_borrower/materialise" '{"rows":[
 {"entity_id":"C1","event_ts":100.0,"ingest_ts":110.0,"dscr":1.20,"ltv":0.62,"monthly_balances":[10,11,12,11,10,9,9,10,11,12,13,12],"correlation":[[1,0.3,0.1],[0.3,1,0.2],[0.1,0.2,1]]},
 {"entity_id":"C2","event_ts":100.0,"ingest_ts":110.0,"dscr":2.10,"ltv":0.35,"monthly_balances":[20,21,22,21,20,19,19,20,21,22,23,22],"correlation":[[1,0,0],[0,1,0],[0,0,1]]},
 {"entity_id":"C1","event_ts":100.0,"ingest_ts":900.0,"dscr":0.40,"ltv":0.81,"monthly_balances":[5,5,4,4,3,3,2,2,1,1,0,0],"correlation":[[1,0.9,0.8],[0.9,1,0.7],[0.8,0.7,1]]}]}' >/dev/null
post "$API/feature-views" '{"name":"qa_outcomes","entity":"borrower","owner":"person/d.raman","features":["defaulted_12m"],"description":"observed outcomes"}' >/dev/null
post "$API/feature-views/qa_outcomes/materialise" '{"rows":[
 {"entity_id":"C1","event_ts":500.0,"ingest_ts":505.0,"defaulted_12m":1},
 {"entity_id":"C2","event_ts":500.0,"ingest_ts":505.0,"defaulted_12m":0}]}' >/dev/null
echo "   qa_borrower v1 (3 rows, one a restatement), qa_outcomes v1"

say "4. a featureset, and a version that pins every slot"
post "$API/featuresets" '{"name":"qa_pd_inputs","entity":"borrower","slots":{"coverage":"numeric","leverage":"numeric","defaulted":"numeric"},"label_slot":"defaulted","outcome_window_days":365,"description":"what the QA PD scorecard reads"}' >/dev/null
post "$API/featuresets/qa_pd_inputs/versions" '{"bindings":{"coverage":"dscr","leverage":"ltv","defaulted":"defaulted_12m"}}' >/dev/null
echo "   qa_pd_inputs v1 — coverage->dscr, leverage->ltv, defaulted->defaulted_12m"

say "5. a model, tiered, with a formula kernel"
post "$API/models" '{"urn":"maya://model/qa.pd.scorecard","name":"QA PD scorecard","model_class":"credit.pd.scorecard","domain":"credit","owner":"person/j.okafor","legal_entity":"LE-US-01","purpose":"12-month probability of default at origination"}' >/dev/null
post "$API/models/qa.pd.scorecard/assess" '{"exposure":250000000,"purpose_class":"credit_decision","feature_count":3,"uses_alternative_data":false,"interpretable":true}' >/dev/null
post "$API/models/qa.pd.scorecard/versions" '{"semver":"1.0.0","kernel":{"runtime":"formula","parameter_kind":"estimated_coefficients","fit_procedure":"estimate","entry":{"expression":"1 / (1 + exp(-(intercept + beta_dscr * dscr + beta_ltv * ltv)))","target":"pd_12m"},"input_schema":[{"name":"dscr","dtype":"numeric","symbol":"\\mathrm{DSCR}","unit":"ratio"},{"name":"ltv","dtype":"numeric","symbol":"\\mathrm{LTV}","unit":"ratio"},{"name":"intercept","dtype":"numeric","symbol":"\\alpha"},{"name":"beta_dscr","dtype":"numeric","symbol":"\\beta_{1}"},{"name":"beta_ltv","dtype":"numeric","symbol":"\\beta_{2}"}],"output_schema":[{"name":"pd_12m","dtype":"numeric","unit":"probability"}]}}' >/dev/null
echo "   maya://model/qa.pd.scorecard @ 1.0.0"

say "done"
echo "Sign in at $BASE  —  admin / maya-admin-dev"
