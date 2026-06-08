import Link from "next/link";

export default function Home() {
  const sections: { title: string; description: string; href?: string }[] = [
    {
      title: "Upload Dataset",
      description: "Upload CSV or Excel files and text context documents.",
    },
    {
      title: "Profile Data",
      description: "Inspect column types, null rates, distributions, and data quality issues.",
    },
    {
      title: "Cleaning Plan",
      description: "Review AI-proposed cleaning steps and approve, reject, or modify each one.",
      href: "/cleaning-plan",
    },
    {
      title: "Feature Engineering",
      description: "Define and approve derived metrics: running revenue, ARPPU, growth rates, and more.",
      href: "/metrics-plan",
    },
    {
      title: "Visualization",
      description: "Explore AI-suggested charts generated from your cleaned, enriched dataset.",
    },
    {
      title: "Insight Report",
      description: "Read a structured insight report grounded in your business context.",
    },
  ];

  return (
    <main className="min-h-screen bg-gray-50 py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-4xl font-bold text-gray-900 mb-3">AI Data Analyst</h1>
        <p className="text-lg text-gray-600 mb-12">
          A structured, human-in-the-loop data analysis workflow. Upload a dataset, review
          AI-generated cleaning and feature plans, and produce inspectable insight reports — without
          writing a single line of code.
        </p>

        <div className="space-y-4">
          {sections.map((section, i) => {
            const card = (
              <div
                className={`bg-white border border-gray-200 rounded-xl p-6 ${
                  section.href ? "hover:border-gray-400 transition-colors" : "opacity-60 cursor-not-allowed"
                }`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-sm font-mono text-gray-400">{String(i + 1).padStart(2, "0")}</span>
                  <h2 className="text-lg font-semibold text-gray-700">{section.title}</h2>
                  <span
                    className={`ml-auto text-xs px-2 py-1 rounded-full ${
                      section.href
                        ? "bg-blue-100 text-blue-600"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {section.href ? "Preview" : "Coming soon"}
                  </span>
                </div>
                <p className="text-sm text-gray-500 ml-9">{section.description}</p>
              </div>
            );
            return section.href ? (
              <Link key={section.title} href={section.href}>
                {card}
              </Link>
            ) : (
              <div key={section.title}>{card}</div>
            );
          })}
        </div>
      </div>
    </main>
  );
}
