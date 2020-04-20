#include <cstdio>
#include <iostream>
#include "database.h"
#include "flagchecker.h"
#include "config.h"
#include "redis.h"
#include <libpq-fe.h>
#include <postgres.h>
#include <catalog/pg_type.h>
#include <unistd.h>

using namespace std;

// use async commits (makes inserts much faster)
#define DB_USE_ASYNC_COMMIT


class DatabaseConnection {
	PGconn *conn = nullptr;

public:
	bool isConnected() {
		return conn != nullptr;
	}

	void connect() {
		if (conn) disconnect();
		conn = PQconnectdb(Config::getPostgresConnectionString());
		if (PQstatus(conn) != CONNECTION_OK) {
			cerr << "[Postgres] Connection broken" << endl;
			disconnect();
			return;
		}

		cerr << "[Postgres] Connection established" << endl;
		prepareStatements();
	}

	void disconnect() {
		if (conn) {
			PQfinish(conn);
			cerr << "[Postgres] Connection closed" << endl;
		}
		conn = nullptr;
	}

	~DatabaseConnection() {
		if (conn != nullptr) disconnect();
	}


private:
	void prepareStatements() {
		// SELECT oid,typname from pg_type;
		Oid params[6] = {INT2OID, INT2OID, INT2OID, INT2OID, INT4OID, INT2OID};
		// Prepare statement (allows pre-planning)
		PGresult *result = PQprepare(conn, "insert_flag",
									 "INSERT INTO submitted_flags (submitted_by, team_id, service_id, round_issued, payload, round_submitted) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING;",
									 6, params);
		if (PQresultStatus(result) != PGRES_COMMAND_OK) {
			cerr << "[Postgres] Could not prepare statement: " << PQerrorMessage(conn);
		}
		PQclear(result);

#ifdef DB_USE_ASYNC_COMMIT
		result = PQexec(conn, "SET SESSION synchronous_commit TO OFF;");
		if (PQresultStatus(result) != PGRES_COMMAND_OK) {
			cerr << "[Postgres] Could not enable asynchronous commits: " << PQerrorMessage(conn);
		}
		PQclear(result);
#endif
	}

public:
	int insertFlag(uint16_t team, FlagFormat &flag) {
		if (!isConnected()) connect();
		if (PQstatus(conn) == CONNECTION_BAD) {
			cerr << "[Postgres] Connection lost" << endl;
			usleep(10000);
			PQreset(conn);
			if (PQstatus(conn) == CONNECTION_BAD) {
				return -1;
			}
			prepareStatements();
		}

		// prepare parameters - libpq wants an array of C-style strings
		string submitting = std::to_string(team);
		string team_id = std::to_string(flag.team_id);
		string service_id = std::to_string(flag.service_id);
		string round_issued = std::to_string((int32_t) flag.round);
		string payload = std::to_string(flag.payload);
		string current_round = std::to_string(Redis::current_round);
		const char *const params[] = {submitting.c_str(), team_id.c_str(), service_id.c_str(), round_issued.c_str(),
									  payload.c_str(), current_round.c_str()};

		// finally insert the flag
		PGresult *result = PQexecPrepared(conn, "insert_flag", 6, params, nullptr, nullptr, 1);
		if (PQresultStatus(result) != PGRES_COMMAND_OK) {
			cerr << "[Postgres] INSERT " << PQerrorMessage(conn);
			PQclear(result);
			return -1;
		}

		// Check if flag has been inserted or not
		const char *affected_rows = PQcmdTuples(result); // possible results: "1", "0", ""
		bool ok = affected_rows[0] == '1';
		PQclear(result);
		return ok ? 1 : 0;
	}


	int getMaxTeamId() {
		if (!isConnected()) connect();

		PGresult* result = PQexec(conn, "SELECT max(id) FROM teams");
		if (PQresultStatus(result) != PGRES_TUPLES_OK) {
			cerr << "[Postgres] SELECT " << PQerrorMessage(conn);
			throw exception();
		}

		if (PQgetisnull(result, 0, 0)){
			return 0;
		}else {
			auto iptr = PQgetvalue(result, 0, 0);
			int maxId = atoi(iptr);
			PQclear(result);
			return maxId;
		}
	}

	int getMaxServiceId() {
		if (!isConnected()) connect();

		PGresult* result = PQexec(conn, "SELECT max(id) FROM services");
		if (PQresultStatus(result) != PGRES_TUPLES_OK) {
			cerr << "[Postgres] SELECT " << PQerrorMessage(conn);
			throw exception();
		}

		if (PQgetisnull(result, 0, 0)){
			return 0;
		}else {
			auto iptr = PQgetvalue(result, 0, 0);
			int maxId = atoi(iptr);
			PQclear(result);
			return maxId;
		}
	}
};


// thread_local - one postgresql connection per worker thread
thread_local DatabaseConnection dbconnection;


int submit_flag(uint16_t team, FlagFormat &flag) {
	return dbconnection.insertFlag(team, flag);
}

int getMaxTeamId(){
	return dbconnection.getMaxTeamId();
}

int getMaxServiceId(){
	return dbconnection.getMaxServiceId();
}
