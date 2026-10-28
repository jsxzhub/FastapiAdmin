import { request } from "@utils";

const API_PATH = "/ops/dbconsole/connection";

export interface DbConnection {
  id: number;
  name: string;
  db_type: "mysql" | "postgres";
  host: string;
  port: number;
  username: string;
  database?: string | null;
  description?: string | null;
  status: number;
  has_password: boolean;
}

export interface DbConnectionForm {
  name: string;
  db_type: "mysql" | "postgres";
  host: string;
  port: number;
  username: string;
  password?: string;
  database?: string | null;
  description?: string | null;
  status?: number;
}

export interface DbQueryResult {
  sql: string;
  read_only: boolean;
  columns: string[];
  rows: unknown[][];
  rowcount: number;
  masked_columns: string[];
  truncated: boolean;
  elapsed_ms: number;
}

export interface DbObject {
  name: string;
}

const DbConsoleAPI = {
  listConnections() {
    return request<ApiResponse<DbConnection[]>>({ url: `${API_PATH}/list`, method: "get" });
  },
  detailConnection(id: number) {
    return request<ApiResponse<DbConnection>>({ url: `${API_PATH}/detail/${id}`, method: "get" });
  },
  createConnection(body: DbConnectionForm) {
    return request<ApiResponse<DbConnection>>({
      url: `${API_PATH}/create`,
      method: "post",
      data: body,
    });
  },
  updateConnection(id: number, body: DbConnectionForm) {
    return request<ApiResponse<DbConnection>>({
      url: `${API_PATH}/update/${id}`,
      method: "put",
      data: body,
    });
  },
  deleteConnections(ids: number[]) {
    return request<ApiResponse<null>>({ url: `${API_PATH}/delete`, method: "delete", data: ids });
  },
  testConnectionConfig(body: DbConnectionForm) {
    return request<ApiResponse<boolean>>({ url: `${API_PATH}/test`, method: "post", data: body });
  },
  testConnection(id: number) {
    return request<ApiResponse<boolean>>({ url: `${API_PATH}/test/${id}`, method: "post" });
  },
  listDatabases(id: number) {
    return request<ApiResponse<DbObject[]>>({ url: `${API_PATH}/${id}/databases`, method: "get" });
  },
  listTables(id: number, database?: string) {
    return request<ApiResponse<DbObject[]>>({
      url: `${API_PATH}/${id}/tables`,
      method: "get",
      params: { database },
    });
  },
  runQuery(id: number, body: { sql: string; confirmed?: boolean }) {
    return request<ApiResponse<DbQueryResult>>({
      url: `${API_PATH}/${id}/query`,
      method: "post",
      data: body,
    });
  },
};

export default DbConsoleAPI;
