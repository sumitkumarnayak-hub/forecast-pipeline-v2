import { redirect } from "next/navigation";

export default function BaselineIndexPage() {
  redirect("/baseline/load-raw");
}
