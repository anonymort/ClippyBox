class Clippybox < Formula
  include Language::Python::Virtualenv

  desc "Point at anything on your screen and instantly understand it"
  homepage "https://github.com/anonymort/clippybox"
  url "https://github.com/anonymort/clippybox/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "UPDATE_AFTER_RELEASE"

  depends_on :macos
  depends_on "python@3.12"
  depends_on "python-tk@3.12"

  # Generate resource blocks with: poet -r requirements.txt
  # resource "openai" do ... end
  # (plus all transitive dependencies)

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "ClippyBox", shell_output("#{bin}/clippybox --version")
  end
end
