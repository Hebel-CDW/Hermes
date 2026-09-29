import { Link } from "react-router-dom";
import { EmptyState } from "../ui/States";

export default function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link className="btn" to="/">
          Go home
        </Link>
      }
    >
      There is no Hermes page at this address.
    </EmptyState>
  );
}
