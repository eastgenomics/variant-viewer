import { Link } from "react-router-dom";

export default function Navbar() {
  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
      <Link
        to="/"
        className="text-blue-700 font-semibold text-lg tracking-tight"
      >
        Variant Viewer
      </Link>
      <Link to="/" className="text-sm text-gray-600 hover:text-gray-900">
        Cases
      </Link>
      <Link to="/upload" className="text-sm text-gray-600 hover:text-gray-900">
        Upload VCF
      </Link>
    </nav>
  );
}
