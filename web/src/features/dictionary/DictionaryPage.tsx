import { get, type Column } from "../../shared/api";
import { Empty, Failed, Loading } from "../../shared/States";
import { useResource } from "../../shared/useResource";

export function DictionaryPage() {
  const res = useResource(() => get<Column[]>("/dictionary"));
  if (res.state === "loading") return <Loading what="the data dictionary" />;
  if (res.state === "error") return <Failed what="the data dictionary" message={res.message} retry={res.retry} />;
  if (res.data.length === 0) return <Empty>No marts yet. Run dbt build to create them.</Empty>;
  const tables = [...new Set(res.data.map((c) => c.table_name))];
  return (
    <section>
      <header className="page-head">
        <h1>What analysts and the product can read</h1>
        <p className="muted">
          The analytics schema, as dbt builds it. Hasura serves the same tables to the read-only scout role; nothing
          below raw carries personal data.
        </p>
      </header>
      {tables.map((t) => (
        <div key={t} className="dict-table">
          <h2>{t}</h2>
          <table className="figures">
            <tbody>
              {res.data.filter((c) => c.table_name === t).map((c) => (
                <tr key={c.column_name}>
                  <td style={{ width: "22%" }}><strong>{c.column_name}</strong></td>
                  <td style={{ width: "14%" }} className="muted">{c.data_type}</td>
                  <td>{c.description ?? <span className="muted">no description yet</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
